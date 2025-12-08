import asyncio
import json
import os
from pathlib import Path
import structlog
from confluent_kafka import Consumer, KafkaError
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from typing import Optional

logger = structlog.get_logger()


class KafkaTicketConsumer:
    '''Consumer Kafka para tópico execution.tickets'''

    def __init__(self, config, execution_engine):
        self.config = config
        self.execution_engine = execution_engine
        self.logger = logger.bind(service='kafka_ticket_consumer')
        self.consumer: Optional[Consumer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_deserializer: Optional[AvroDeserializer] = None
        self.running = False

    async def initialize(self):
        '''Inicializar consumer Kafka'''
        try:
            consumer_config = {
                'bootstrap.servers': self.config.kafka_bootstrap_servers,
                'group.id': self.config.kafka_consumer_group_id,
                'auto.offset.reset': self.config.kafka_auto_offset_reset,
                'enable.auto.commit': False
            }

            consumer_config.update(self._configure_security())
            self.consumer = Consumer(consumer_config)

            try:
                schema_path = Path(self.config.schemas_base_path) / 'execution-ticket' / 'execution-ticket.avsc'
                schema_str = schema_path.read_text()

                self.schema_registry_client = SchemaRegistryClient(
                    {'url': self.config.kafka_schema_registry_url}
                )
                self.avro_deserializer = AvroDeserializer(self.schema_registry_client, schema_str)
                self.logger.info(
                    'schema_registry_enabled',
                    url=self.config.kafka_schema_registry_url
                )
            except Exception as exc:
                self.logger.warning(
                    'schema_registry_unavailable_fallback_json',
                    error=str(exc)
                )
                self.schema_registry_client = None
                self.avro_deserializer = None

            self.consumer.subscribe([self.config.kafka_tickets_topic])

            self.logger.info(
                'kafka_consumer_initialized',
                topic=self.config.kafka_tickets_topic,
                group_id=self.config.kafka_consumer_group_id
            )

            # TODO: Incrementar métrica worker_agent_kafka_consumer_initialized_total

        except Exception as e:
            self.logger.error('kafka_consumer_init_failed', error=str(e))
            raise

    async def start(self):
        '''Iniciar loop de consumo'''
        self.running = True

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

                ticket = None

                if not self.running:
                    break

                try:
                    context = SerializationContext(
                        message.topic(), MessageField.VALUE
                    )

                    if self.avro_deserializer:
                        ticket = self.avro_deserializer(message.value(), context)
                    else:
                        ticket = json.loads(message.value().decode('utf-8'))

                    # Validar campos obrigatórios
                    required_fields = ['ticket_id', 'task_id', 'task_type', 'status', 'dependencies']
                    missing_fields = [f for f in required_fields if f not in ticket]
                    if missing_fields:
                        self.logger.warning(
                            'invalid_ticket_missing_fields',
                            ticket_id=ticket.get('ticket_id'),
                            missing_fields=missing_fields
                        )
                        await asyncio.get_event_loop().run_in_executor(
                            None, lambda: self.consumer.commit(message)
                        )
                        continue

                    # Verificar se task_type é suportado
                    task_type = ticket.get('task_type')
                    if task_type not in self.config.supported_task_types:
                        self.logger.warning(
                            'unsupported_task_type',
                            ticket_id=ticket.get('ticket_id'),
                            task_type=task_type
                        )
                        await asyncio.get_event_loop().run_in_executor(
                            None, lambda: self.consumer.commit(message)
                        )
                        continue

                    # Verificar status
                    status = ticket.get('status')
                    if status != 'PENDING':
                        self.logger.debug(
                            'skipping_non_pending_ticket',
                            ticket_id=ticket.get('ticket_id'),
                            status=status
                        )
                        await asyncio.get_event_loop().run_in_executor(
                            None, lambda: self.consumer.commit(message)
                        )
                        continue

                    # Processar ticket
                    self.logger.info(
                        'ticket_consumed',
                        ticket_id=ticket.get('ticket_id'),
                        task_type=task_type,
                        plan_id=ticket.get('plan_id')
                    )

                    # TODO: Incrementar métrica worker_agent_tickets_consumed_total{task_type=...}

                    await self.execution_engine.process_ticket(ticket)

                    # Commit offset após processamento bem-sucedido
                    await asyncio.get_event_loop().run_in_executor(
                        None, lambda: self.consumer.commit(message)
                    )

                except Exception as e:
                    self.logger.error(
                        'ticket_processing_failed',
                        ticket_id=ticket.get('ticket_id') if isinstance(ticket, dict) else None,
                        error=str(e),
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset
                    )
                    # Não commit - permite retry
                    # TODO: Incrementar métrica worker_agent_kafka_consumer_errors_total{error_type=...}

        except Exception as e:
            self.logger.error('kafka_consumer_loop_failed', error=str(e))
            raise
        finally:
            self.running = False

    async def stop(self):
        '''Parar consumer'''
        self.running = False
        if self.consumer:
            await asyncio.get_event_loop().run_in_executor(None, self.consumer.close)
            self.logger.info('kafka_consumer_stopped')

    def _configure_security(self) -> dict:
        """Configuração de segurança Kafka (SASL/SSL)."""
        security_config = {
            'security.protocol': self.config.kafka_security_protocol
        }

        if self.config.kafka_security_protocol in ['SASL_SSL', 'SASL_PLAINTEXT']:
            if getattr(self.config, 'kafka_sasl_mechanism', None):
                security_config['sasl.mechanism'] = self.config.kafka_sasl_mechanism
            if self.config.kafka_sasl_username and self.config.kafka_sasl_password:
                security_config['sasl.username'] = self.config.kafka_sasl_username
                security_config['sasl.password'] = self.config.kafka_sasl_password

        if self.config.kafka_security_protocol in ['SSL', 'SASL_SSL']:
            if getattr(self.config, 'kafka_ssl_ca_location', None):
                security_config['ssl.ca.location'] = self.config.kafka_ssl_ca_location
            if getattr(self.config, 'kafka_ssl_certificate_location', None):
                security_config['ssl.certificate.location'] = self.config.kafka_ssl_certificate_location
            if getattr(self.config, 'kafka_ssl_key_location', None):
                security_config['ssl.key.location'] = self.config.kafka_ssl_key_location

        return security_config
