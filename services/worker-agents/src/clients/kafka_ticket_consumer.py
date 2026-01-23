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
    '''Consumer Kafka para topico execution.tickets'''

    def __init__(self, config, execution_engine, metrics=None):
        self.config = config
        self.execution_engine = execution_engine
        self.metrics = metrics
        self.logger = logger.bind(service='kafka_ticket_consumer')
        self.consumer: Optional[Consumer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_deserializer: Optional[AvroDeserializer] = None
        self.running = False
        self.redis_client = None  # Sera injetado via initialize()

    async def initialize(self, redis_client=None):
        '''Inicializar consumer Kafka'''
        self.redis_client = redis_client
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

            if self.metrics:
                self.metrics.kafka_consumer_initialized_total.inc()

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

                    if self.metrics:
                        self.metrics.tickets_consumed_total.labels(task_type=task_type).inc()

                    await self.execution_engine.process_ticket(ticket)

                    # Limpar contador de retries apos sucesso
                    await self._clear_retry_count(ticket.get('ticket_id'))

                    # Commit offset apos processamento bem-sucedido
                    await asyncio.get_event_loop().run_in_executor(
                        None, lambda: self.consumer.commit(message)
                    )

                except Exception as e:
                    ticket_id_for_log = ticket.get('ticket_id') if isinstance(ticket, dict) else None

                    # Incrementar contador de retries
                    retry_count = await self._increment_retry_count(ticket_id_for_log) if ticket_id_for_log else 1

                    # Verificar se excedeu limite de retries
                    max_retries = getattr(self.config, 'kafka_max_retries_before_dlq', 3)

                    if retry_count >= max_retries:
                        self.logger.error(
                            'ticket_max_retries_exceeded_sending_to_dlq',
                            ticket_id=ticket_id_for_log,
                            retry_count=retry_count,
                            max_retries=max_retries,
                            error=str(e)
                        )

                        # Publicar no DLQ
                        await self._publish_to_dlq(ticket, e, retry_count)

                        # Limpar contador de retries
                        if ticket_id_for_log:
                            await self._clear_retry_count(ticket_id_for_log)

                        # Commit offset para nao reprocessar
                        await asyncio.get_event_loop().run_in_executor(
                            None, lambda: self.consumer.commit(message)
                        )
                    else:
                        self.logger.error(
                            'ticket_processing_failed_will_retry',
                            ticket_id=ticket_id_for_log,
                            retry_count=retry_count,
                            max_retries=max_retries,
                            error=str(e),
                            topic=message.topic(),
                            partition=message.partition(),
                            offset=message.offset()
                        )
                        # Nao commit - permite retry via Kafka redelivery

                    if self.metrics:
                        error_type = type(e).__name__
                        self.metrics.kafka_consumer_errors_total.labels(error_type=error_type).inc()

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

    async def _get_retry_count(self, ticket_id: str) -> int:
        """
        Obter contador de retries do Redis.

        Args:
            ticket_id: ID do execution ticket

        Returns:
            Numero de tentativas de processamento (0 se nao existe)
        """
        if not self.redis_client:
            self.logger.warning('redis_not_available_retry_count_unavailable')
            return 0

        try:
            retry_key = f"ticket:retry_count:{ticket_id}"
            count = await self.redis_client.get(retry_key)
            return int(count) if count else 0
        except Exception as e:
            self.logger.error('get_retry_count_failed', ticket_id=ticket_id, error=str(e))
            return 0  # Fail-open: assumir 0 retries em caso de erro

    async def _increment_retry_count(self, ticket_id: str) -> int:
        """
        Incrementar contador de retries no Redis.

        Args:
            ticket_id: ID do execution ticket

        Returns:
            Novo valor do contador
        """
        if not self.redis_client:
            self.logger.warning('redis_not_available_cannot_increment_retry')
            return 1  # Fail-open: assumir primeira tentativa

        try:
            retry_key = f"ticket:retry_count:{ticket_id}"
            # Incrementar com TTL de 7 dias (alinhado com retention do topico)
            new_count = await self.redis_client.incr(retry_key)
            await self.redis_client.expire(retry_key, 604800)  # 7 dias

            self.logger.debug(
                'retry_count_incremented',
                ticket_id=ticket_id,
                retry_count=new_count
            )

            return new_count
        except Exception as e:
            self.logger.error('increment_retry_count_failed', ticket_id=ticket_id, error=str(e))
            return 1  # Fail-open

    async def _clear_retry_count(self, ticket_id: str):
        """
        Limpar contador de retries apos sucesso.

        Args:
            ticket_id: ID do execution ticket
        """
        if not self.redis_client:
            return

        try:
            retry_key = f"ticket:retry_count:{ticket_id}"
            await self.redis_client.delete(retry_key)
            self.logger.debug('retry_count_cleared', ticket_id=ticket_id)
        except Exception as e:
            self.logger.error('clear_retry_count_failed', ticket_id=ticket_id, error=str(e))

    async def _publish_to_dlq(self, ticket: dict, error: Exception, retry_count: int):
        """
        Publicar ticket no Dead Letter Queue.

        Args:
            ticket: Execution ticket original
            error: Excecao que causou a falha
            retry_count: Numero de tentativas de processamento
        """
        import time
        from datetime import datetime
        from confluent_kafka import Producer

        ticket_id = ticket.get('ticket_id', 'unknown')
        task_type = ticket.get('task_type', 'unknown')

        start_time = time.time()

        try:
            # Enriquecer ticket com metadata de DLQ
            dlq_message = {
                **ticket,
                'dlq_metadata': {
                    'original_error': str(error),
                    'error_type': type(error).__name__,
                    'retry_count': retry_count,
                    'last_failure_timestamp': int(datetime.now().timestamp() * 1000),
                    'dlq_published_at': int(datetime.now().timestamp() * 1000)
                }
            }

            # Publicar no topico DLQ
            dlq_topic = getattr(self.config, 'kafka_dlq_topic', 'execution.tickets.dlq')

            # Usar producer simples (JSON) para DLQ
            producer_config = {
                'bootstrap.servers': self.config.kafka_bootstrap_servers,
                'acks': 'all',
                'retries': 3,
                'enable.idempotence': True
            }
            producer_config.update(self._configure_security())

            producer = Producer(producer_config)

            # Serializar como JSON
            message_value = json.dumps(dlq_message).encode('utf-8')

            delivery_result = {'success': False, 'error': None}

            # Publicar com callback
            def delivery_callback(err, msg):
                if err:
                    delivery_result['error'] = err
                    self.logger.error(
                        'dlq_publish_failed',
                        ticket_id=ticket_id,
                        error=str(err)
                    )
                    if self.metrics:
                        self.metrics.dlq_publish_errors_total.labels(error_type=type(err).__name__).inc()
                else:
                    delivery_result['success'] = True
                    self.logger.info(
                        'dlq_publish_success',
                        ticket_id=ticket_id,
                        partition=msg.partition(),
                        offset=msg.offset()
                    )

            producer.produce(
                topic=dlq_topic,
                key=ticket_id.encode('utf-8'),
                value=message_value,
                callback=delivery_callback
            )

            producer.flush(timeout=10)

            duration = time.time() - start_time

            self.logger.warning(
                'ticket_sent_to_dlq',
                ticket_id=ticket_id,
                task_type=task_type,
                retry_count=retry_count,
                error=str(error),
                duration_seconds=duration
            )

            if self.metrics:
                self.metrics.dlq_messages_total.labels(
                    reason='max_retries_exceeded',
                    task_type=task_type
                ).inc()
                self.metrics.dlq_publish_duration_seconds.observe(duration)
                self.metrics.ticket_retry_count.labels(task_type=task_type).observe(retry_count)

        except Exception as dlq_error:
            self.logger.error(
                'dlq_publish_exception',
                ticket_id=ticket_id,
                error=str(dlq_error),
                exc_info=True
            )
            if self.metrics:
                self.metrics.dlq_publish_errors_total.labels(error_type=type(dlq_error).__name__).inc()
            # Nao propagar excecao - ja estamos em error handling
