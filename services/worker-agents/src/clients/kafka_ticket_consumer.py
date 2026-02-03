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

        # Backpressure control
        self.tickets_semaphore = None  # Inicializado em initialize()
        self.in_flight_tickets: set = set()  # Rastrear ticket_ids em processamento
        self.consumer_paused = False
        self.pause_start_time = None

        # Lock para serializar chamadas a Consumer.commit (evita race conditions)
        self._commit_lock = asyncio.Lock()

    async def initialize(self, redis_client=None):
        '''Inicializar consumer Kafka'''
        self.redis_client = redis_client

        # Inicializar semaphore de backpressure
        max_concurrent = getattr(self.config, 'max_concurrent_tickets', 10)
        self.tickets_semaphore = asyncio.Semaphore(max_concurrent)

        self.logger.info(
            'backpressure_initialized',
            max_concurrent_tickets=max_concurrent
        )

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
                # Verificar se deve resumir consumer
                await self._resume_consumer_if_needed()

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

                    # Auto-detect format: Avro (magic byte 0x00) vs JSON (starts with '{')
                    raw_value = message.value()
                    is_avro_format = raw_value and len(raw_value) > 5 and raw_value[0] == 0x00

                    if is_avro_format and self.avro_deserializer:
                        ticket = self.avro_deserializer(raw_value, context)
                    else:
                        # Fallback to JSON for legacy messages or when Schema Registry unavailable
                        ticket = json.loads(raw_value.decode('utf-8'))

                    # Validar campos obrigatórios
                    required_fields = ['ticket_id', 'task_id', 'task_type', 'status', 'dependencies']
                    missing_fields = [f for f in required_fields if f not in ticket]
                    if missing_fields:
                        self.logger.warning(
                            'invalid_ticket_missing_fields',
                            ticket_id=ticket.get('ticket_id'),
                            missing_fields=missing_fields
                        )
                        await self._commit_with_lock(message)
                        continue

                    # Verificar se task_type é suportado
                    task_type = ticket.get('task_type')
                    if task_type not in self.config.supported_task_types:
                        self.logger.warning(
                            'unsupported_task_type',
                            ticket_id=ticket.get('ticket_id'),
                            task_type=task_type
                        )
                        await self._commit_with_lock(message)
                        continue

                    # Verificar status
                    status = ticket.get('status')
                    if status != 'PENDING':
                        self.logger.debug(
                            'skipping_non_pending_ticket',
                            ticket_id=ticket.get('ticket_id'),
                            status=status
                        )
                        await self._commit_with_lock(message)
                        continue

                    # Adquirir semaphore de backpressure (bloqueia se limite atingido)
                    await self.tickets_semaphore.acquire()

                    ticket_id = ticket.get('ticket_id')
                    self.in_flight_tickets.add(ticket_id)

                    # Atualizar métrica
                    if self.metrics:
                        self.metrics.tickets_in_flight.set(len(self.in_flight_tickets))

                    # Verificar se deve pausar consumer
                    await self._pause_consumer_if_needed()

                    # Processar ticket em background task
                    self.logger.info(
                        'ticket_consumed',
                        ticket_id=ticket_id,
                        task_type=task_type,
                        plan_id=ticket.get('plan_id'),
                        in_flight_tickets=len(self.in_flight_tickets)
                    )

                    if self.metrics:
                        self.metrics.tickets_consumed_total.labels(task_type=task_type).inc()

                    # Criar background task para processamento
                    asyncio.create_task(
                        self._process_ticket_with_cleanup(ticket, message)
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

                        # Construir payload seguro para DLQ
                        dlq_payload = self._build_dlq_payload(ticket, message)

                        # Publicar no DLQ com retry/backoff
                        dlq_success = await self._publish_to_dlq(dlq_payload, e, retry_count)

                        if dlq_success:
                            # Limpar contador de retries apenas se DLQ publicou com sucesso
                            if ticket_id_for_log:
                                await self._clear_retry_count(ticket_id_for_log)

                            # Commit offset apenas se DLQ publicou com sucesso
                            await self._commit_with_lock(message)
                        else:
                            # DLQ falhou - não fazer commit para reprocessar
                            self.logger.error(
                                'dlq_publish_failed_will_retry_message',
                                ticket_id=ticket_id_for_log,
                                retry_count=retry_count
                            )
                            # Não fazer commit - mensagem será reprocessada
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

    def _should_pause_consumer(self) -> bool:
        """
        Verificar se consumer deve ser pausado por backpressure.

        Returns:
            True se deve pausar, False caso contrário
        """
        if not self.tickets_semaphore:
            return False

        max_concurrent = self.tickets_semaphore._value + len(self.in_flight_tickets)
        threshold = getattr(self.config, 'consumer_pause_threshold', 0.8)
        pause_limit = int(max_concurrent * threshold)

        return len(self.in_flight_tickets) >= pause_limit

    def _should_resume_consumer(self) -> bool:
        """
        Verificar se consumer deve ser resumido após backpressure.

        Returns:
            True se deve resumir, False caso contrário
        """
        if not self.tickets_semaphore or not self.consumer_paused:
            return False

        max_concurrent = self.tickets_semaphore._value + len(self.in_flight_tickets)
        threshold = getattr(self.config, 'consumer_resume_threshold', 0.5)
        resume_limit = int(max_concurrent * threshold)

        return len(self.in_flight_tickets) <= resume_limit

    async def _pause_consumer_if_needed(self):
        """
        Pausar consumer se threshold de backpressure atingido.
        """
        if self._should_pause_consumer() and not self.consumer_paused:
            self.consumer.pause(self.consumer.assignment())
            self.consumer_paused = True
            self.pause_start_time = asyncio.get_event_loop().time()

            self.logger.warning(
                'consumer_paused_backpressure',
                in_flight_tickets=len(self.in_flight_tickets),
                max_concurrent=self.tickets_semaphore._value + len(self.in_flight_tickets)
            )

            if self.metrics:
                self.metrics.consumer_paused_total.inc()
                self.metrics.tickets_in_flight.set(len(self.in_flight_tickets))

    async def _resume_consumer_if_needed(self):
        """
        Resumir consumer se threshold de resume atingido.
        """
        if self._should_resume_consumer():
            self.consumer.resume(self.consumer.assignment())
            self.consumer_paused = False

            if self.pause_start_time:
                pause_duration = asyncio.get_event_loop().time() - self.pause_start_time

                self.logger.info(
                    'consumer_resumed_backpressure',
                    in_flight_tickets=len(self.in_flight_tickets),
                    pause_duration_seconds=pause_duration
                )

                if self.metrics:
                    self.metrics.consumer_resumed_total.inc()
                    self.metrics.consumer_pause_duration_seconds.observe(pause_duration)

                self.pause_start_time = None

            if self.metrics:
                self.metrics.tickets_in_flight.set(len(self.in_flight_tickets))

    async def _process_ticket_with_cleanup(self, ticket: dict, message):
        """
        Processar ticket e fazer cleanup de backpressure após conclusão.

        Implementa lógica completa de retry/DLQ para falhas em process_ticket.

        Args:
            ticket: Execution ticket deserializado
            message: Mensagem Kafka original
        """
        ticket_id = ticket.get('ticket_id')
        task_type = ticket.get('task_type', 'unknown')
        should_commit = False

        try:
            # Processar ticket via execution engine
            await self.execution_engine.process_ticket(ticket)

            # Limpar contador de retries após sucesso
            await self._clear_retry_count(ticket_id)

            # Marcar para commit
            should_commit = True

        except Exception as e:
            # Incrementar contador de retries
            retry_count = await self._increment_retry_count(ticket_id)
            max_retries = getattr(self.config, 'kafka_max_retries_before_dlq', 3)

            if retry_count >= max_retries:
                self.logger.error(
                    'ticket_max_retries_exceeded_sending_to_dlq',
                    ticket_id=ticket_id,
                    task_type=task_type,
                    retry_count=retry_count,
                    max_retries=max_retries,
                    error=str(e)
                )

                # Publicar no DLQ com retry/backoff
                dlq_success = await self._publish_to_dlq(ticket, e, retry_count)

                if dlq_success:
                    # Limpar contador de retries após DLQ publicado
                    await self._clear_retry_count(ticket_id)
                    # Commit apenas se DLQ publicou com sucesso
                    should_commit = True
                else:
                    # DLQ falhou - não fazer commit para reprocessar
                    self.logger.error(
                        'dlq_publish_failed_will_retry_message',
                        ticket_id=ticket_id,
                        retry_count=retry_count
                    )
            else:
                self.logger.error(
                    'ticket_processing_failed_will_retry',
                    ticket_id=ticket_id,
                    task_type=task_type,
                    retry_count=retry_count,
                    max_retries=max_retries,
                    error=str(e)
                )
                # Não fazer commit - permite retry via Kafka redelivery

            if self.metrics:
                error_type = type(e).__name__
                self.metrics.kafka_consumer_errors_total.labels(error_type=error_type).inc()

        finally:
            # Commit offset se marcado para commit (sucesso ou DLQ confirmado)
            if should_commit:
                await self._commit_with_lock(message)

            # Cleanup de backpressure (sempre executado)
            if ticket_id in self.in_flight_tickets:
                self.in_flight_tickets.remove(ticket_id)

            # Liberar semaphore
            self.tickets_semaphore.release()

            # Atualizar métrica
            if self.metrics:
                self.metrics.tickets_in_flight.set(len(self.in_flight_tickets))

            self.logger.debug(
                'ticket_cleanup_completed',
                ticket_id=ticket_id,
                in_flight_tickets=len(self.in_flight_tickets)
            )

    async def _commit_with_lock(self, message):
        """
        Commit offset com lock para serializar chamadas concorrentes.

        Evita comportamento indefinido quando múltiplas tasks tentam
        chamar Consumer.commit() em paralelo.

        Args:
            message: Mensagem Kafka para commit
        """
        async with self._commit_lock:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.consumer.commit(message)
            )

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

    def _build_dlq_payload(self, ticket, message) -> dict:
        """
        Construir payload seguro para DLQ, tratando casos de deserialização falha.

        Se ticket não for um dict válido, constrói um payload mínimo com
        informações da mensagem Kafka original para análise forense.

        Args:
            ticket: Ticket deserializado (pode ser None ou tipo inválido)
            message: Mensagem Kafka original

        Returns:
            Dict com payload seguro para DLQ
        """
        if isinstance(ticket, dict) and ticket:
            return ticket

        # Ticket inválido - construir payload mínimo (Comment 3)
        raw_value = None
        try:
            if message.value():
                raw_value = message.value().decode('utf-8', errors='replace')[:1000]  # Limitar tamanho
        except Exception:
            raw_value = '<falha ao decodificar mensagem>'

        minimal_payload = {
            'ticket_id': 'unknown',
            'task_id': 'unknown',
            'task_type': 'unknown',
            'status': 'DESERIALIZATION_FAILED',
            'dependencies': [],
            '_deserialization_error': True,
            '_raw_message_preview': raw_value,
            '_kafka_metadata': {
                'topic': message.topic(),
                'partition': message.partition(),
                'offset': message.offset(),
                'timestamp': message.timestamp()[1] if message.timestamp() else None
            }
        }

        self.logger.warning(
            'ticket_deserialization_failed_using_minimal_payload',
            topic=message.topic(),
            partition=message.partition(),
            offset=message.offset(),
            raw_preview=raw_value[:100] if raw_value else None
        )

        return minimal_payload

    async def _publish_to_dlq(self, ticket: dict, error: Exception, retry_count: int) -> bool:
        """
        Publicar ticket no Dead Letter Queue com retry e backoff.

        Implementa retry com backoff exponencial para garantir que a mensagem
        seja publicada no DLQ antes de fazer commit do offset. (Comment 1)

        Args:
            ticket: Execution ticket original (já validado por _build_dlq_payload)
            error: Excecao que causou a falha
            retry_count: Numero de tentativas de processamento

        Returns:
            bool: True se publicação foi bem-sucedida, False caso contrário
        """
        import time
        from datetime import datetime
        from confluent_kafka import Producer

        ticket_id = ticket.get('ticket_id', 'unknown')
        task_type = ticket.get('task_type', 'unknown')

        # Configurações de retry do DLQ (com fallback para valores default)
        max_retries_val = getattr(self.config, 'dlq_publish_max_retries', None)
        max_retries = max_retries_val if isinstance(max_retries_val, int) else 3

        backoff_base_val = getattr(self.config, 'dlq_publish_retry_backoff_base_seconds', None)
        backoff_base = backoff_base_val if isinstance(backoff_base_val, (int, float)) else 1.0

        backoff_max_val = getattr(self.config, 'dlq_publish_retry_backoff_max_seconds', None)
        backoff_max = backoff_max_val if isinstance(backoff_max_val, (int, float)) else 30.0

        start_time = time.time()

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

        # Serializar como JSON
        try:
            message_value = json.dumps(dlq_message).encode('utf-8')
        except Exception as serialize_error:
            self.logger.error(
                'dlq_serialization_failed',
                ticket_id=ticket_id,
                error=str(serialize_error)
            )
            return False

        # Retry loop com backoff exponencial (Comment 1)
        for attempt in range(max_retries):
            try:
                producer = Producer(producer_config)
                delivery_result = {'success': False, 'error': None}

                # Publicar com callback
                def delivery_callback(err, msg):
                    if err:
                        delivery_result['error'] = err
                    else:
                        delivery_result['success'] = True

                producer.produce(
                    topic=dlq_topic,
                    key=ticket_id.encode('utf-8'),
                    value=message_value,
                    callback=delivery_callback
                )

                # Flush com timeout
                producer.flush(timeout=10)

                if delivery_result['success']:
                    duration = time.time() - start_time

                    self.logger.info(
                        'dlq_publish_success',
                        ticket_id=ticket_id,
                        task_type=task_type,
                        attempt=attempt + 1,
                        duration_seconds=duration
                    )

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

                    return True
                else:
                    # Delivery callback reportou erro
                    raise Exception(f"Kafka delivery failed: {delivery_result['error']}")

            except Exception as dlq_error:
                self.logger.warning(
                    'dlq_publish_attempt_failed',
                    ticket_id=ticket_id,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(dlq_error)
                )

                if attempt < max_retries - 1:
                    # Calcular backoff exponencial
                    backoff_time = min(backoff_base * (2 ** attempt), backoff_max)
                    self.logger.debug(
                        'dlq_publish_retry_backoff',
                        ticket_id=ticket_id,
                        backoff_seconds=backoff_time
                    )
                    await asyncio.sleep(backoff_time)

        # Todas as tentativas falharam
        self.logger.error(
            'dlq_publish_all_retries_exhausted',
            ticket_id=ticket_id,
            max_retries=max_retries,
            error=str(error)
        )

        if self.metrics:
            self.metrics.dlq_publish_errors_total.labels(error_type='all_retries_exhausted').inc()

        return False
