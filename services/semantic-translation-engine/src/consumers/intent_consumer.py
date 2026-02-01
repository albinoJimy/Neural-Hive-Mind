"""
Intent Consumer - Kafka transactional consumer for Intent Envelopes

Consumes Intent Envelopes from Kafka with exactly-once semantics.
"""

import asyncio
import os
import structlog
import json
import time
from typing import Optional, Callable, Dict
from confluent_kafka import Consumer, KafkaError, TopicPartition
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer

from neural_hive_observability.context import extract_context_from_headers, set_baggage

from src.config.settings import Settings

logger = structlog.get_logger()


class IntentConsumer:
    """Kafka consumer for Intent Envelopes"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.consumer: Optional[Consumer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_deserializer: Optional[AvroDeserializer] = None
        self.running = False
        self.last_poll_time: Optional[float] = None
        self.messages_processed: int = 0

    async def initialize(self):
        """Initialize Kafka consumer com validação robusta de tópicos e assignments"""
        logger.info(
            'Iniciando inicialização do Intent Consumer',
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            consumer_group=self.settings.kafka_consumer_group_id,
            topics=self.settings.kafka_topics,
            auto_offset_reset=self.settings.kafka_auto_offset_reset,
            security_protocol=self.settings.kafka_security_protocol
        )

        consumer_config = {
            'bootstrap.servers': self.settings.kafka_bootstrap_servers,
            'group.id': self.settings.kafka_consumer_group_id,
            'auto.offset.reset': self.settings.kafka_auto_offset_reset,
            'enable.auto.commit': False,  # Manual commit for transactions
            'isolation.level': 'read_committed',  # Exactly-once semantics
            'session.timeout.ms': self.settings.kafka_session_timeout_ms,

            # Fix for Kafka connection termination issue
            'connections.max.idle.ms': 540000,  # 9 minutes
            'socket.keepalive.enable': True,
            'heartbeat.interval.ms': 3000,
            'max.poll.interval.ms': 300000,  # 5 minutes
        }

        # Add security configuration
        if self.settings.kafka_security_protocol != 'PLAINTEXT':
            consumer_config.update({
                'security.protocol': self.settings.kafka_security_protocol,
                'sasl.mechanism': self.settings.kafka_sasl_mechanism,
                'sasl.username': self.settings.kafka_sasl_username,
                'sasl.password': self.settings.kafka_sasl_password,
            })

        self.consumer = Consumer(consumer_config)
        logger.info(
            'Consumer Kafka criado',
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            consumer_group=self.settings.kafka_consumer_group_id
        )

        # Validar existência de tópicos antes de fazer subscribe
        logger.info('Validating Kafka topics existence', topics=self.settings.kafka_topics)

        try:
            cluster_metadata = self.consumer.list_topics(timeout=10)
            available_topics = set(cluster_metadata.topics.keys())

            missing_topics = [
                topic for topic in self.settings.kafka_topics
                if topic not in available_topics
            ]

            if missing_topics:
                logger.error(
                    'Tópicos Kafka obrigatórios não encontrados',
                    missing_topics=missing_topics,
                    configured_topics=self.settings.kafka_topics,
                    available_topics=sorted(list(available_topics))[:20]  # Limitar output
                )
                raise RuntimeError(
                    f"Tópicos Kafka não encontrados: {missing_topics}. "
                    f"Verifique se os tópicos foram criados no cluster. "
                    f"Tópicos disponíveis: {sorted(list(available_topics))[:10]}"
                )

            logger.info(
                'Todos os tópicos configurados existem no cluster',
                topics=self.settings.kafka_topics,
                total_available_topics=len(available_topics)
            )

        except RuntimeError:
            # Re-raise RuntimeError para não mascarar erros de tópicos
            raise
        except Exception as e:
            logger.error(
                'Falha ao validar tópicos Kafka',
                error=str(e),
                error_type=type(e).__name__
            )
            raise RuntimeError(f"Não foi possível validar tópicos Kafka: {e}") from e

        # Subscribe aos tópicos
        logger.info('Subscribing to Kafka topics', topics=self.settings.kafka_topics)
        self.consumer.subscribe(self.settings.kafka_topics)

        # Aguardar assignments com polling ativo
        logger.info('Aguardando consumer assignments (timeout: 30s)')
        max_wait_seconds = 30
        poll_interval_seconds = 0.5
        start_time = time.time()
        assignments_received = False

        while time.time() - start_time < max_wait_seconds:
            # Poll para disparar rebalance - armazenar resultado para não perder mensagens
            msg = self.consumer.poll(timeout=0.1)

            # Se recebeu mensagem válida durante espera de assignments, fazer seek para reprocessar
            if msg is not None and not msg.error():
                tp = TopicPartition(msg.topic(), msg.partition(), msg.offset())
                self.consumer.seek(tp)
                logger.debug(
                    'Mensagem recebida durante espera de assignments - seek realizado',
                    topic=msg.topic(),
                    partition=msg.partition(),
                    offset=msg.offset()
                )

            # Verificar assignments
            assignments = self.consumer.assignment()
            if assignments:
                assignment_info = [
                    f"{tp.topic}:{tp.partition}"
                    for tp in assignments
                ]
                logger.info(
                    'Consumer assignments recebidos',
                    assignments=assignment_info,
                    total_partitions=len(assignments),
                    elapsed_seconds=round(time.time() - start_time, 2)
                )
                assignments_received = True
                break

            await asyncio.sleep(poll_interval_seconds)

        if not assignments_received:
            logger.error(
                'Timeout aguardando consumer assignments',
                timeout_seconds=max_wait_seconds,
                consumer_group=self.settings.kafka_consumer_group_id,
                topics=self.settings.kafka_topics
            )
            raise RuntimeError(
                f"Consumer não recebeu assignments após {max_wait_seconds}s. "
                f"Verifique se o consumer group '{self.settings.kafka_consumer_group_id}' "
                f"está configurado corretamente e se há partições disponíveis nos tópicos."
            )

        # Initialize Schema Registry client (optional for dev)
        if self.settings.schema_registry_url and self.settings.schema_registry_url.strip():
            schema_path = '/app/schemas/intent-envelope/intent-envelope.avsc'

            if os.path.exists(schema_path):
                self.schema_registry_client = SchemaRegistryClient({'url': self.settings.schema_registry_url})

                # Load Avro schema
                with open(schema_path, 'r') as f:
                    schema_str = f.read()

                self.avro_deserializer = AvroDeserializer(
                    self.schema_registry_client,
                    schema_str
                )
                logger.info('Schema Registry enabled for consumer', url=self.settings.schema_registry_url)
            else:
                logger.error('Avro schema not found', path=schema_path)
                logger.warning('Falling back to JSON deserialization')
                self.schema_registry_client = None
                self.avro_deserializer = None
        else:
            logger.warning('Schema Registry disabled - using JSON deserialization for dev')
            self.schema_registry_client = None
            self.avro_deserializer = None

        logger.info(
            'Intent consumer inicializado com sucesso',
            topics=self.settings.kafka_topics,
            group_id=self.settings.kafka_consumer_group_id,
            assignments=len(self.consumer.assignment()) if self.consumer else 0,
            schema_registry_enabled=self.avro_deserializer is not None
        )

    async def start_consuming(self, processor_callback: Callable):
        """
        Start consuming messages

        Args:
            processor_callback: Async function to process IntentEnvelope
        """
        self.running = True

        logger.info('Starting consumer loop')

        # Run consumer loop asynchronously with non-blocking poll
        await self._consume_async_loop(processor_callback)

        logger.info('Consumer loop stopped')

    async def _consume_async_loop(self, processor_callback: Callable):
        """
        Asynchronous consumer loop with non-blocking poll

        Args:
            processor_callback: Async function to process IntentEnvelope
        """
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="kafka-poller")

        poll_count = 0
        logger.info('Consumer loop initialized, starting to poll...')

        while self.running:
            try:
                # Poll with short timeout (non-blocking)
                # Run in executor to avoid blocking the event loop
                loop = asyncio.get_running_loop()
                msg = await loop.run_in_executor(
                    executor,
                    self.consumer.poll,
                    1.0
                )

                poll_count += 1
                self.last_poll_time = time.time()

                # Log every 60 polls (~60 seconds) to confirm loop is running
                if poll_count % 60 == 0:
                    logger.debug(f'Consumer loop active, poll count: {poll_count}')

                if msg is None:
                    await asyncio.sleep(0.1)  # Small delay to avoid busy loop
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        logger.error('Kafka consumer error', error=msg.error())
                        continue

                # Log message reception
                logger.info(
                    'Message received from Kafka',
                    topic=msg.topic(),
                    partition=msg.partition(),
                    offset=msg.offset()
                )

                # Deserialize message
                intent_envelope = self._deserialize_message(msg)

                # Extract W3C trace context from Kafka headers (traceparent)
                headers_dict = {k: v.decode('utf-8') if isinstance(v, bytes) else v
                                for k, v in (msg.headers() or [])}
                extract_context_from_headers(headers_dict)

                # Set baggage for correlation
                intent_id = intent_envelope.get('id')
                if intent_id:
                    set_baggage('neural.hive.intent.id', intent_id)

                # Extract legacy trace context (deprecated, mantido para compatibilidade)
                trace_context = self._extract_trace_context(msg.headers() or [])

                # Process message in same event loop
                try:
                    # Run async processor directly in current event loop
                    await processor_callback(intent_envelope, trace_context)

                    # Commit offset after successful processing
                    # Run commit in executor to avoid blocking
                    await loop.run_in_executor(
                        executor,
                        lambda: self.consumer.commit(asynchronous=False)
                    )

                    self.messages_processed += 1
                    logger.debug(
                        'Message processed',
                        intent_id=intent_envelope.get('id'),
                        topic=msg.topic(),
                        partition=msg.partition(),
                        offset=msg.offset(),
                        total_processed=self.messages_processed
                    )

                except Exception as e:
                    logger.error(
                        'Error processing message',
                        error=str(e),
                        intent_id=intent_envelope.get('id') if intent_envelope else None
                    )
                    # Don't commit offset on error - message will be retried

            except Exception as e:
                logger.error('Error in consumer loop', error=str(e))
                await asyncio.sleep(1.0)  # Back off on error

        # Cleanup executor
        executor.shutdown(wait=True)

    def _deserialize_message(self, msg) -> Dict:
        """
        Deserializa mensagem Kafka para IntentEnvelope

        Suporta deserialização Avro (via Schema Registry) e JSON fallback.
        Usa auto-detecção robusta: tenta Avro primeiro se configurado,
        depois JSON como fallback.

        Args:
            msg: Mensagem Kafka

        Returns:
            Dict do IntentEnvelope
        """
        # Extrair content-type dos headers (para logging)
        headers = msg.headers() or []
        content_type = None
        for key, value in headers:
            if key == 'content-type':
                content_type = value.decode('utf-8') if value else None
                break

        raw_value = msg.value()

        # Estratégia 1: Se content-type indica Avro E temos deserializer
        if content_type == 'application/avro' and self.avro_deserializer:
            try:
                serialization_context = SerializationContext(msg.topic(), MessageField.VALUE)
                data = self.avro_deserializer(raw_value, serialization_context)
                logger.debug(
                    'Mensagem deserializada (Avro via header)',
                    intent_id=data.get('id'),
                    domain=data.get('intent', {}).get('domain')
                )
                return data
            except Exception as e:
                logger.warning(
                    'Falha ao deserializar Avro apesar do header, tentando JSON',
                    error=str(e),
                    content_type=content_type
                )

        # Estratégia 2: Se content-type indica JSON
        if content_type == 'application/json':
            try:
                data = json.loads(raw_value.decode('utf-8'))
                logger.debug(
                    'Mensagem deserializada (JSON via header)',
                    intent_id=data.get('id'),
                    domain=data.get('intent', {}).get('domain')
                )
                return data
            except Exception as e:
                logger.warning(
                    'Falha ao deserializar JSON apesar do header',
                    error=str(e),
                    content_type=content_type
                )

        # Estratégia 3: Auto-detecção - tentar Avro primeiro se configurado
        if self.avro_deserializer:
            try:
                serialization_context = SerializationContext(msg.topic(), MessageField.VALUE)
                data = self.avro_deserializer(raw_value, serialization_context)
                logger.debug(
                    'Mensagem deserializada (Avro auto-detectado)',
                    intent_id=data.get('id'),
                    domain=data.get('intent', {}).get('domain'),
                    content_type=content_type
                )
                return data
            except Exception as avro_error:
                logger.debug(
                    'Auto-detecção: Avro falhou, tentando JSON',
                    avro_error=str(avro_error)
                )

        # Estratégia 4: Fallback final para JSON
        try:
            data = json.loads(raw_value.decode('utf-8'))
            logger.debug(
                'Mensagem deserializada (JSON fallback)',
                intent_id=data.get('id'),
                domain=data.get('intent', {}).get('domain'),
                content_type=content_type
            )
            return data
        except Exception as json_error:
            logger.error(
                'Falha em todas as estratégias de deserialização',
                json_error=str(json_error),
                content_type=content_type,
                raw_value_preview=raw_value[:100] if raw_value else None,
                avro_deserializer_configured=self.avro_deserializer is not None
            )
            raise ValueError(
                f"Não foi possível deserializar mensagem. "
                f"content-type={content_type}, "
                f"avro_configured={self.avro_deserializer is not None}"
            )

    def _extract_trace_context(self, headers: list) -> Dict[str, str]:
        """
        Extract legacy trace context from headers (deprecated).

        NOTA: Esta função é mantida para compatibilidade com headers customizados
        (trace-id, span-id, correlation-id). O contexto W3C traceparent é extraído
        via extract_context_from_headers() em _consume_async_loop.

        Args:
            headers: Kafka message headers

        Returns:
            Trace context dict
        """
        trace_context = {}

        for key, value in headers:
            if key == 'trace-id':
                trace_context['trace_id'] = value.decode('utf-8')
            elif key == 'span-id':
                trace_context['span_id'] = value.decode('utf-8')
            elif key == 'correlation-id':
                trace_context['correlation_id'] = value.decode('utf-8')

        # Log de debug para rastrear extração de headers
        logger.debug(
            'Trace context extraído dos headers Kafka',
            trace_id=trace_context.get('trace_id'),
            span_id=trace_context.get('span_id'),
            correlation_id=trace_context.get('correlation_id'),
            total_headers=len(headers)
        )

        # Warning se correlation_id não foi encontrado nos headers
        if 'correlation_id' not in trace_context:
            logger.warning(
                'correlation_id ausente nos headers Kafka',
                headers_presentes=[key for key, _ in headers]
            )

        return trace_context

    async def close(self):
        """Close consumer gracefully"""
        self.running = False
        if self.consumer:
            self.consumer.close()
            logger.info('Intent consumer fechado')

    def is_healthy(self, max_poll_age_seconds: float = 60.0) -> tuple[bool, str]:
        """
        Verifica se o consumer está saudável baseado em atividade recente.

        Args:
            max_poll_age_seconds: Tempo máximo em segundos desde o último poll

        Returns:
            Tuple de (is_healthy, reason)
        """
        if not self.running:
            return False, "Consumer não está em estado running"

        if not self.consumer:
            return False, "Consumer Kafka não inicializado"

        if self.last_poll_time is None:
            return False, "Consumer ainda não iniciou polling"

        poll_age = time.time() - self.last_poll_time
        if poll_age > max_poll_age_seconds:
            return False, f"Último poll há {poll_age:.1f}s (máx: {max_poll_age_seconds}s)"

        return True, f"Consumer ativo (último poll há {poll_age:.1f}s, {self.messages_processed} msgs processadas)"
