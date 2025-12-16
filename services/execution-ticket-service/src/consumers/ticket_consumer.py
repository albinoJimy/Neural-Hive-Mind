"""
Kafka Consumer para consumir tickets do tópico execution.tickets.
"""
import asyncio
import logging
import json
from pathlib import Path
from typing import Optional
from confluent_kafka import Consumer, KafkaError
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer

from neural_hive_observability import instrument_kafka_consumer
from neural_hive_observability.context import (
    extract_context_from_headers,
    set_baggage
)

from ..config import get_settings
from ..models import ExecutionTicket
from ..database import get_postgres_client, get_mongodb_client
from ..models.jwt_token import generate_token
from ..observability.metrics import TicketServiceMetrics

logger = logging.getLogger(__name__)


class TicketConsumer:
    """Consumer Kafka para processar Execution Tickets."""

    def __init__(self, settings, metrics: TicketServiceMetrics):
        """Inicializa consumer."""
        self.settings = settings
        self.metrics = metrics
        self.consumer: Optional[Consumer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_deserializer: Optional[AvroDeserializer] = None
        self.running = False

    async def start(self):
        """Inicia consumer Kafka."""
        try:
            consumer_config = {
                'bootstrap.servers': self.settings.kafka_bootstrap_servers,
                'group.id': self.settings.kafka_consumer_group_id,
                'auto.offset.reset': self.settings.kafka_auto_offset_reset,
                'enable.auto.commit': False
            }

            consumer_config.update(self._configure_security())
            self.consumer = Consumer(consumer_config)
            self.consumer = instrument_kafka_consumer(self.consumer)

            try:
                schema_path = Path(self.settings.schemas_base_path) / 'execution-ticket' / 'execution-ticket.avsc'
                schema_str = schema_path.read_text()

                self.schema_registry_client = SchemaRegistryClient(
                    {'url': self.settings.kafka_schema_registry_url}
                )
                self.avro_deserializer = AvroDeserializer(self.schema_registry_client, schema_str)
                logger.info("Schema Registry habilitado para consumer", url=self.settings.kafka_schema_registry_url)
            except Exception as exc:
                logger.warning("Schema Registry indisponível - fallback para JSON", error=str(exc))
                self.schema_registry_client = None
                self.avro_deserializer = None

            self.consumer.subscribe([self.settings.kafka_tickets_topic])

            self.running = True
            logger.info(
                "Kafka consumer started",
                topic=self.settings.kafka_tickets_topic,
                group_id=self.settings.kafka_consumer_group_id
            )

        except Exception as e:
            logger.error(f"Failed to start Kafka consumer: {e}", exc_info=True)
            raise

    async def stop(self):
        """Para consumer Kafka."""
        self.running = False
        if self.consumer:
            await asyncio.get_event_loop().run_in_executor(None, self.consumer.close)
            logger.info("Kafka consumer stopped")

    async def consume(self):
        """Loop principal de consumo de mensagens."""
        if not self.consumer:
            raise RuntimeError("Consumer not started")

        logger.info("Starting message consumption loop")

        try:
            while self.running:
                message = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.consumer.poll(timeout=1.0)
                )

                if message is None:
                    continue

                if message.error():
                    if message.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    raise message.error()

                try:
                    serialization_context = SerializationContext(
                        message.topic(), MessageField.VALUE
                    )

                    headers_dict = {k: v for k, v in (message.headers() or [])}
                    extract_context_from_headers(headers_dict)

                    if self.avro_deserializer:
                        ticket_dict = self.avro_deserializer(message.value(), serialization_context)
                    else:
                        ticket_dict = json.loads(message.value().decode('utf-8'))

                    # Converter para Pydantic
                    ticket = ExecutionTicket.from_avro_dict(ticket_dict)
                    if ticket.plan_id:
                        set_baggage("plan_id", ticket.plan_id)
                    if ticket.ticket_id:
                        set_baggage("ticket_id", ticket.ticket_id)

                    # Processar ticket
                    await self._process_ticket(ticket)

                    # Commit manual
                    if not self.settings.kafka_enable_auto_commit:
                        await asyncio.get_event_loop().run_in_executor(
                            None, lambda: self.consumer.commit(message)
                        )

                    # Métricas
                    self.metrics.tickets_consumed_total.inc()
                    self.metrics.kafka_messages_consumed_total.inc()

                except Exception as e:
                    logger.error(
                        f"Error processing message",
                        error=str(e),
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset,
                        exc_info=True
                    )
                    self.metrics.tickets_processing_errors_total.inc()
                    # Não commit em caso de erro (retry)

        except asyncio.CancelledError:
            logger.info("Consumption loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Fatal error in consumption loop: {e}", exc_info=True)
            raise

    async def _process_ticket(self, ticket: ExecutionTicket):
        """
        Processa ticket consumido do Kafka.

        Args:
            ticket: ExecutionTicket consumido
        """
        logger.info(
            f"Processing ticket {ticket.ticket_id}",
            plan_id=ticket.plan_id,
            task_type=ticket.task_type.value,
            status=ticket.status.value
        )

        try:
            # 1. Persistir no PostgreSQL
            postgres_client = await get_postgres_client()
            await postgres_client.create_ticket(ticket)
            logger.debug(f"Ticket persisted in PostgreSQL", ticket_id=ticket.ticket_id)

            # 2. Persistir no MongoDB (audit trail)
            if self.settings.enable_audit_trail:
                mongodb_client = await get_mongodb_client()
                await mongodb_client.save_ticket_audit(ticket)
                logger.debug(f"Ticket audit saved in MongoDB", ticket_id=ticket.ticket_id)

            # 3. Gerar token JWT
            if self.settings.enable_jwt_tokens:
                token = generate_token(
                    ticket,
                    self.settings.jwt_secret_key,
                    self.settings.jwt_algorithm,
                    self.settings.jwt_token_expiration_seconds
                )

                # Adicionar token ao metadata (opcional - pode ser consultado via API)
                logger.debug(
                    f"JWT token generated",
                    ticket_id=ticket.ticket_id,
                    expires_at=token.expires_at
                )
                self.metrics.jwt_tokens_generated_total.inc()

            # 4. Disparar webhook (se configurado)
            if self.settings.enable_webhooks and 'webhook_url' in ticket.metadata:
                webhook_url = ticket.metadata['webhook_url']

                # TODO: Enfileirar webhook no WebhookManager
                # webhook_event = WebhookEvent(
                #     event_id=str(uuid.uuid4()),
                #     event_type='ticket.created',
                #     ticket_id=ticket.ticket_id,
                #     ticket=ticket,
                #     timestamp=int(time.time() * 1000),
                #     webhook_url=webhook_url
                # )
                # await webhook_manager.enqueue_webhook(webhook_event)

                logger.debug(
                    f"Webhook enqueued",
                    ticket_id=ticket.ticket_id,
                    webhook_url=webhook_url
                )

            # Métricas
            self.metrics.tickets_persisted_total.inc()
            self.metrics.tickets_by_status.labels(status=ticket.status.value).set(1)

            logger.info(
                f"Ticket processed successfully",
                ticket_id=ticket.ticket_id,
                duration_ms=10  # TODO: medir tempo real
            )

        except Exception as e:
            logger.error(
                f"Error processing ticket {ticket.ticket_id}: {e}",
                plan_id=ticket.plan_id,
                exc_info=True
            )
            raise

    def _configure_security(self) -> dict:
        """Retorna config de segurança Kafka (SASL/SSL)."""
        security_config = {
            'security.protocol': self.settings.kafka_security_protocol
        }

        if self.settings.kafka_security_protocol in ['SASL_SSL', 'SASL_PLAINTEXT']:
            if getattr(self.settings, 'kafka_sasl_mechanism', None):
                security_config['sasl.mechanism'] = self.settings.kafka_sasl_mechanism
            if self.settings.kafka_sasl_username and self.settings.kafka_sasl_password:
                security_config['sasl.username'] = self.settings.kafka_sasl_username
                security_config['sasl.password'] = self.settings.kafka_sasl_password

        if self.settings.kafka_security_protocol in ['SSL', 'SASL_SSL']:
            if getattr(self.settings, 'kafka_ssl_ca_location', None):
                security_config['ssl.ca.location'] = self.settings.kafka_ssl_ca_location
            if getattr(self.settings, 'kafka_ssl_certificate_location', None):
                security_config['ssl.certificate.location'] = self.settings.kafka_ssl_certificate_location
            if getattr(self.settings, 'kafka_ssl_key_location', None):
                security_config['ssl.key.location'] = self.settings.kafka_ssl_key_location

        return security_config


async def start_ticket_consumer(metrics: TicketServiceMetrics) -> TicketConsumer:
    """
    Factory function para criar e iniciar consumer.

    Args:
        metrics: Instância de TicketServiceMetrics

    Returns:
        TicketConsumer iniciado
    """
    settings = get_settings()
    consumer = TicketConsumer(settings, metrics)
    await consumer.start()
    return consumer
