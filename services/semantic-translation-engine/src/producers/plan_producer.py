"""
Plan Producer - Kafka transactional producer for Cognitive Plans

Publishes Cognitive Plans to Kafka with exactly-once semantics.
"""

import os
import structlog
import json
from typing import Optional
from confluent_kafka import Producer, KafkaError
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer

from src.config.settings import Settings

logger = structlog.get_logger()


class KafkaPlanProducer:
    """Kafka producer for Cognitive Plans"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.producer: Optional[Producer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_serializer: Optional[AvroSerializer] = None
        self._transactional_id = self._generate_transactional_id()

    def _generate_transactional_id(self) -> str:
        """Gera ID transacional estável por pod"""
        hostname = os.environ.get('HOSTNAME', 'local')
        pod_uid = os.environ.get('POD_UID', '0')
        return f'semantic-translation-engine-{hostname}-{pod_uid}'

    async def initialize(self):
        """Inicializa producer Kafka com suporte a Schema Registry"""
        producer_config = {
            'bootstrap.servers': self.settings.kafka_bootstrap_servers,
            'enable.idempotence': self.settings.kafka_enable_idempotence,
            'transactional.id': self._transactional_id,
            'acks': 'all',
            'max.in.flight.requests.per.connection': 5,
        }

        # Add security configuration
        if self.settings.kafka_security_protocol != 'PLAINTEXT':
            producer_config.update({
                'security.protocol': self.settings.kafka_security_protocol,
                'sasl.mechanism': self.settings.kafka_sasl_mechanism,
                'sasl.username': self.settings.kafka_sasl_username,
                'sasl.password': self.settings.kafka_sasl_password,
            })

        self.producer = Producer(producer_config)

        # Initialize Schema Registry client (optional for dev)
        if self.settings.schema_registry_url and self.settings.schema_registry_url.strip():
            schema_path = '/app/schemas/cognitive-plan.avsc'

            if os.path.exists(schema_path):
                self.schema_registry_client = SchemaRegistryClient({'url': self.settings.schema_registry_url})

                # Load Avro schema
                with open(schema_path, 'r') as f:
                    schema_str = f.read()

                self.avro_serializer = AvroSerializer(
                    self.schema_registry_client,
                    schema_str
                )
                logger.info('Schema Registry enabled for producer', url=self.settings.schema_registry_url)
            else:
                logger.error('Avro schema not found', path=schema_path)
                logger.warning('Falling back to JSON serialization')
                self.schema_registry_client = None
                self.avro_serializer = None
        else:
            logger.warning('Schema Registry disabled - using JSON serialization for dev')
            self.schema_registry_client = None
            self.avro_serializer = None

        # Initialize transactions
        self.producer.init_transactions()

        logger.info(
            'Plan producer inicializado',
            transactional_id=self._transactional_id,
            topic=self.settings.kafka_plans_topic
        )

    async def send_plan(
        self,
        cognitive_plan,
        topic_override: Optional[str] = None
    ):
        """
        Envia Cognitive Plan para Kafka com serialização Avro

        Utiliza Schema Registry quando disponível para serialização Avro.
        Fallback para JSON quando Schema Registry não está configurado (dev).

        Args:
            cognitive_plan: Instância de CognitivePlan
            topic_override: Tópico opcional para override
        """
        topic = topic_override or self.settings.kafka_plans_topic

        try:
            # Begin transaction
            self.producer.begin_transaction()

            # Serialize plan (Avro ou JSON)
            if self.avro_serializer:
                # Serializar usando Avro
                avro_data = cognitive_plan.to_avro_dict()
                serialization_context = SerializationContext(topic, MessageField.VALUE)
                value = self.avro_serializer(avro_data, serialization_context)
                content_type = 'application/avro'
            else:
                # Fallback para JSON quando Schema Registry não disponível
                value = json.dumps(
                    cognitive_plan.to_avro_dict(),
                    default=str
                ).encode('utf-8')
                content_type = 'application/json'

            # Prepare headers
            headers = [
                ('plan-id', cognitive_plan.plan_id.encode('utf-8')),
                ('intent-id', cognitive_plan.intent_id.encode('utf-8')),
                ('risk-band', cognitive_plan.risk_band.value.encode('utf-8')),
                ('schema-version', b'1'),
                ('content-type', content_type.encode('utf-8')),
            ]

            if cognitive_plan.correlation_id:
                headers.append(
                    ('correlation-id', cognitive_plan.correlation_id.encode('utf-8'))
                )

            if cognitive_plan.trace_id:
                headers.append(
                    ('trace-id', cognitive_plan.trace_id.encode('utf-8'))
                )

            if cognitive_plan.span_id:
                headers.append(
                    ('span-id', cognitive_plan.span_id.encode('utf-8'))
                )

            # Partition key by domain
            key = cognitive_plan.get_partition_key().encode('utf-8')

            # Produce message
            self.producer.produce(
                topic=topic,
                key=key,
                value=value,
                headers=headers,
                on_delivery=self._delivery_callback
            )

            # Flush
            self.producer.flush()

            # Commit transaction
            self.producer.commit_transaction()

            logger.info(
                'Plan publicado',
                plan_id=cognitive_plan.plan_id,
                intent_id=cognitive_plan.intent_id,
                topic=topic,
                risk_band=cognitive_plan.risk_band.value,
                size_bytes=len(value),
                format=content_type
            )

        except Exception as e:
            logger.error(
                'Erro ao publicar plan',
                plan_id=cognitive_plan.plan_id,
                error=str(e)
            )

            # Abort transaction on error
            self.producer.abort_transaction()
            raise

    def _delivery_callback(self, err, msg):
        """Callback de entrega de mensagens produzidas"""
        if err:
            logger.error(
                'Falha na entrega do plan',
                error=err,
                topic=msg.topic()
            )
        else:
            logger.debug(
                'Plan entregue',
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset()
            )

    async def close(self):
        """Fecha producer gracefully"""
        if self.producer:
            self.producer.flush()
            logger.info('Plan producer fechado')
