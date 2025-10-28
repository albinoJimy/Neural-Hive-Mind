"""
Intent Consumer - Kafka transactional consumer for Intent Envelopes

Consumes Intent Envelopes from Kafka with exactly-once semantics.
"""

import asyncio
import os
import structlog
import json
from typing import Optional, Callable, Dict
from confluent_kafka import Consumer, KafkaError
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer

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

    async def initialize(self):
        """Initialize Kafka consumer"""
        consumer_config = {
            'bootstrap.servers': self.settings.kafka_bootstrap_servers,
            'group.id': self.settings.kafka_consumer_group_id,
            'auto.offset.reset': self.settings.kafka_auto_offset_reset,
            'enable.auto.commit': False,  # Manual commit for transactions
            'isolation.level': 'read_committed',  # Exactly-once semantics
            'session.timeout.ms': self.settings.kafka_session_timeout_ms,
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
        self.consumer.subscribe(self.settings.kafka_topics)

        # Initialize Schema Registry client (optional for dev)
        if self.settings.schema_registry_url and self.settings.schema_registry_url.strip():
            schema_path = '/app/schemas/intent-envelope.avsc'

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
            'Intent consumer inicializado',
            topics=self.settings.kafka_topics,
            group_id=self.settings.kafka_consumer_group_id
        )

    async def start_consuming(self, processor_callback: Callable):
        """
        Start consuming messages

        Args:
            processor_callback: Async function to process IntentEnvelope
        """
        self.running = True

        logger.info('Starting consumer loop')

        # Run blocking consumer in thread
        await asyncio.to_thread(self._consume_sync_loop, processor_callback)

        logger.info('Consumer loop stopped')

    def _consume_sync_loop(self, processor_callback: Callable):
        """
        Synchronous consumer loop running in thread

        Args:
            processor_callback: Async function to process IntentEnvelope
        """
        while self.running:
            try:
                # Poll with timeout
                msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        logger.error('Kafka consumer error', error=msg.error())
                        continue

                # Deserialize message
                intent_envelope = self._deserialize_message(msg)

                # Extract trace context from headers
                trace_context = self._extract_trace_context(msg.headers() or [])

                # Process message in event loop
                try:
                    # Create a new event loop for this thread if needed
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                    # Run async processor in the event loop
                    loop.run_until_complete(processor_callback(intent_envelope, trace_context))

                    # Commit offset after successful processing
                    self.consumer.commit(asynchronous=False)

                    logger.debug(
                        'Message processed',
                        intent_id=intent_envelope.get('id'),
                        topic=msg.topic(),
                        partition=msg.partition(),
                        offset=msg.offset()
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

    def _deserialize_message(self, msg) -> Dict:
        """
        Deserializa mensagem Kafka para IntentEnvelope

        Suporta deserialização Avro (via Schema Registry) e JSON fallback.
        Detecta o formato através do header 'content-type'.

        Args:
            msg: Mensagem Kafka

        Returns:
            Dict do IntentEnvelope
        """
        try:
            # Extrair content-type dos headers
            headers = msg.headers() or []
            content_type = None
            for key, value in headers:
                if key == 'content-type':
                    content_type = value.decode('utf-8') if value else None
                    break

            # Deserializar baseado no content-type
            if content_type == 'application/avro' and self.avro_deserializer:
                # Deserializar usando Avro
                serialization_context = SerializationContext(msg.topic(), MessageField.VALUE)
                data = self.avro_deserializer(msg.value(), serialization_context)

                logger.debug(
                    'Mensagem deserializada (Avro)',
                    intent_id=data.get('id'),
                    domain=data.get('intent', {}).get('domain')
                )
            else:
                # Fallback para JSON
                data = json.loads(msg.value().decode('utf-8'))

                logger.debug(
                    'Mensagem deserializada (JSON fallback)',
                    intent_id=data.get('id'),
                    domain=data.get('intent', {}).get('domain'),
                    content_type=content_type
                )

            return data

        except Exception as e:
            logger.error('Erro ao deserializar mensagem', error=str(e))
            raise

    def _extract_trace_context(self, headers: list) -> Dict[str, str]:
        """
        Extract OpenTelemetry trace context from headers

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

        return trace_context

    async def close(self):
        """Close consumer gracefully"""
        self.running = False
        if self.consumer:
            self.consumer.close()
            logger.info('Intent consumer fechado')
