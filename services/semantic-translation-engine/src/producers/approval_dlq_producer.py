"""
Approval DLQ Producer - Kafka transactional producer para Dead Letter Queue

Publica planos aprovados que falharam na republicação após esgotamento de retries.
Suporta serialização Avro quando Schema Registry está configurado, com fallback para JSON.
"""

import os
import structlog
import json
from typing import Optional
from confluent_kafka import Producer
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer

from src.config.settings import Settings
from src.models.approval_dlq import ApprovalDLQEntry

logger = structlog.get_logger()


class ApprovalDLQProducer:
    """
    Kafka producer para Dead Letter Queue de aprovações.

    Suporta serialização Avro quando Schema Registry está configurado,
    com fallback automático para JSON quando não disponível.
    """

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
        return f'approval-dlq-producer-{hostname}-{pod_uid}'

    async def initialize(self):
        """Inicializa producer Kafka transacional com suporte a Schema Registry"""
        producer_config = {
            'bootstrap.servers': self.settings.kafka_bootstrap_servers,
            'enable.idempotence': self.settings.kafka_enable_idempotence,
            'transactional.id': self._transactional_id,
            'acks': 'all',
            'max.in.flight.requests.per.connection': 5,
        }

        # Adicionar configurações de segurança se necessário
        if self.settings.kafka_security_protocol != 'PLAINTEXT':
            producer_config.update({
                'security.protocol': self.settings.kafka_security_protocol,
                'sasl.mechanism': self.settings.kafka_sasl_mechanism,
                'sasl.username': self.settings.kafka_sasl_username,
                'sasl.password': self.settings.kafka_sasl_password,
            })

        self.producer = Producer(producer_config)

        # Inicializar Schema Registry client (opcional)
        if self.settings.schema_registry_url and self.settings.schema_registry_url.strip():
            schema_path = '/app/schemas/approval-dlq/approval-dlq.avsc'
            logger.info(
                'Inicializando Schema Registry para DLQ producer',
                url=self.settings.schema_registry_url,
                schema_path=schema_path
            )

            if os.path.exists(schema_path):
                logger.info('Schema Avro DLQ encontrado', path=schema_path, size_bytes=os.path.getsize(schema_path))
                self.schema_registry_client = SchemaRegistryClient({'url': self.settings.schema_registry_url})

                # Carregar schema Avro
                with open(schema_path, 'r') as f:
                    schema_str = f.read()

                self.avro_serializer = AvroSerializer(
                    self.schema_registry_client,
                    schema_str
                )
                logger.info(
                    'Schema Registry habilitado para DLQ producer',
                    url=self.settings.schema_registry_url,
                    schema_path=schema_path,
                    serializer_type='AvroSerializer'
                )
            else:
                logger.warning(
                    'Schema Avro DLQ não encontrado - fallback para JSON',
                    path=schema_path,
                    expected_location='/app/schemas/approval-dlq/approval-dlq.avsc'
                )
                self.schema_registry_client = None
                self.avro_serializer = None
        else:
            logger.warning(
                'Schema Registry desabilitado para DLQ - usando serialização JSON',
                schema_registry_url=self.settings.schema_registry_url
            )
            self.schema_registry_client = None
            self.avro_serializer = None

        # Inicializar transações
        self.producer.init_transactions()

        logger.info(
            'Approval DLQ producer inicializado',
            transactional_id=self._transactional_id,
            topic=self.settings.kafka_approval_dlq_topic,
            serialization='avro' if self.avro_serializer else 'json'
        )

    async def send_dlq_entry(self, dlq_entry: ApprovalDLQEntry) -> None:
        """
        Envia entrada para Dead Letter Queue.

        Utiliza Schema Registry quando disponível para serialização Avro.
        Fallback para JSON quando Schema Registry não está configurado.

        Args:
            dlq_entry: Entrada DLQ com informações da falha
        """
        topic = self.settings.kafka_approval_dlq_topic

        try:
            # Iniciar transação
            self.producer.begin_transaction()

            # Serializar (Avro ou JSON)
            avro_data = dlq_entry.to_avro_dict()

            if self.avro_serializer:
                # Serializar usando Avro
                serialization_context = SerializationContext(topic, MessageField.VALUE)
                value = self.avro_serializer(avro_data, serialization_context)
                content_type = 'application/avro'
            else:
                # Fallback para JSON quando Schema Registry não disponível
                value = json.dumps(avro_data, default=str).encode('utf-8')
                content_type = 'application/json'

            # Preparar headers
            headers = [
                ('plan-id', dlq_entry.plan_id.encode('utf-8')),
                ('intent-id', dlq_entry.intent_id.encode('utf-8')),
                ('retry-count', str(dlq_entry.retry_count).encode('utf-8')),
                ('schema-version', b'1'),
                ('content-type', content_type.encode('utf-8')),
            ]

            if dlq_entry.correlation_id:
                headers.append(
                    ('correlation-id', dlq_entry.correlation_id.encode('utf-8'))
                )

            if dlq_entry.trace_id:
                headers.append(
                    ('trace-id', dlq_entry.trace_id.encode('utf-8'))
                )

            if dlq_entry.span_id:
                headers.append(
                    ('span-id', dlq_entry.span_id.encode('utf-8'))
                )

            if dlq_entry.risk_band:
                headers.append(
                    ('risk-band', dlq_entry.risk_band.encode('utf-8'))
                )

            # Partition key por plan_id para garantir ordem
            key = dlq_entry.plan_id.encode('utf-8')

            # Produzir mensagem
            self.producer.produce(
                topic=topic,
                key=key,
                value=value,
                headers=headers,
                on_delivery=self._delivery_callback
            )

            # Flush
            self.producer.flush()

            # Commit transação
            self.producer.commit_transaction()

            logger.info(
                'Entrada DLQ publicada com sucesso',
                plan_id=dlq_entry.plan_id,
                intent_id=dlq_entry.intent_id,
                topic=topic,
                retry_count=dlq_entry.retry_count,
                size_bytes=len(value),
                format=content_type
            )

        except Exception as e:
            logger.error(
                'Erro ao publicar entrada na DLQ',
                plan_id=dlq_entry.plan_id,
                error=str(e)
            )

            # Abortar transação em caso de erro
            try:
                self.producer.abort_transaction()
            except Exception:
                pass
            raise

    def _delivery_callback(self, err, msg):
        """Callback de entrega de mensagens produzidas"""
        if err:
            logger.error(
                'Falha na entrega da mensagem DLQ',
                error=err,
                topic=msg.topic()
            )
        else:
            logger.debug(
                'Mensagem DLQ entregue',
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset()
            )

    async def close(self):
        """Fecha producer gracefully"""
        if self.producer:
            self.producer.flush()
            logger.info('Approval DLQ producer fechado')
