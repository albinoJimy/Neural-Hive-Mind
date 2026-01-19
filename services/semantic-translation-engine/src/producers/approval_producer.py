"""
Approval Producer - Kafka transactional producer para planos que requerem aprovacao

Publica Cognitive Plans que precisam de aprovacao humana para o topico de aprovacao
com semantica exactly-once.
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


class KafkaApprovalProducer:
    """Kafka producer para Cognitive Plans que requerem aprovacao"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.producer: Optional[Producer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_serializer: Optional[AvroSerializer] = None
        self._transactional_id = self._generate_transactional_id()

    def _generate_transactional_id(self) -> str:
        """Gera ID transacional estavel por pod"""
        hostname = os.environ.get('HOSTNAME', 'local')
        pod_uid = os.environ.get('POD_UID', '0')
        return f'approval-producer-{hostname}-{pod_uid}'

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
            schema_path = '/app/schemas/cognitive-plan/cognitive-plan.avsc'
            logger.info(
                'Inicializando Schema Registry para approval producer',
                url=self.settings.schema_registry_url,
                schema_path=schema_path
            )

            if os.path.exists(schema_path):
                logger.info('Schema Avro encontrado para approval producer', path=schema_path)
                self.schema_registry_client = SchemaRegistryClient({'url': self.settings.schema_registry_url})

                # Load Avro schema
                with open(schema_path, 'r') as f:
                    schema_str = f.read()

                self.avro_serializer = AvroSerializer(
                    self.schema_registry_client,
                    schema_str
                )
                logger.info(
                    'Schema Registry habilitado para approval producer',
                    url=self.settings.schema_registry_url,
                    serializer_type='AvroSerializer'
                )
            else:
                logger.warning(
                    'Schema Avro nao encontrado para approval producer - fallback para JSON',
                    path=schema_path
                )
                self.schema_registry_client = None
                self.avro_serializer = None
        else:
            logger.warning(
                'Schema Registry desabilitado para approval producer - usando JSON',
                environment=self.settings.environment if hasattr(self.settings, 'environment') else 'unknown'
            )

        # Initialize transactions
        self.producer.init_transactions()

        logger.info(
            'Approval producer inicializado',
            transactional_id=self._transactional_id,
            topic=self.settings.kafka_approval_topic
        )

    async def send_approval_request(self, cognitive_plan):
        """
        Envia Cognitive Plan para topico de aprovacao com serializacao Avro

        Utiliza Schema Registry quando disponivel para serializacao Avro.
        Fallback para JSON quando Schema Registry nao esta configurado (dev).

        Args:
            cognitive_plan: Instancia de CognitivePlan que requer aprovacao
        """
        topic = self.settings.kafka_approval_topic

        try:
            # Begin transaction
            self.producer.begin_transaction()

            # Serialize plan (Avro ou JSON)
            if self.avro_serializer:
                avro_data = cognitive_plan.to_avro_dict()
                serialization_context = SerializationContext(topic, MessageField.VALUE)
                value = self.avro_serializer(avro_data, serialization_context)
                content_type = 'application/avro'
            else:
                value = json.dumps(
                    cognitive_plan.to_avro_dict(),
                    default=str
                ).encode('utf-8')
                content_type = 'application/json'

            # Prepare headers com contexto de aprovacao
            risk_band_value = (
                cognitive_plan.risk_band.value
                if hasattr(cognitive_plan.risk_band, 'value')
                else cognitive_plan.risk_band
            )

            headers = [
                ('plan-id', cognitive_plan.plan_id.encode('utf-8')),
                ('intent-id', cognitive_plan.intent_id.encode('utf-8')),
                ('risk-band', risk_band_value.encode('utf-8')),
                ('is-destructive', str(cognitive_plan.is_destructive).lower().encode('utf-8')),
                ('schema-version', b'1'),
                ('content-type', content_type.encode('utf-8')),
                ('requires-approval', b'true'),
            ]

            # Adicionar severidade destrutiva se disponivel
            if cognitive_plan.risk_matrix and 'destructive_severity' in cognitive_plan.risk_matrix:
                headers.append(
                    ('destructive-severity', str(cognitive_plan.risk_matrix['destructive_severity']).encode('utf-8'))
                )

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
                'Plan publicado no topico de aprovacao',
                plan_id=cognitive_plan.plan_id,
                intent_id=cognitive_plan.intent_id,
                topic=topic,
                risk_band=risk_band_value,
                is_destructive=cognitive_plan.is_destructive,
                size_bytes=len(value),
                format=content_type
            )

        except Exception as e:
            logger.error(
                'Erro ao publicar plan para aprovacao',
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
                'Falha na entrega do plan para aprovacao',
                error=err,
                topic=msg.topic()
            )
        else:
            logger.debug(
                'Plan entregue ao topico de aprovacao',
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset()
            )

    async def close(self):
        """Fecha producer gracefully"""
        if self.producer:
            self.producer.flush()
            logger.info('Approval producer fechado')
