"""
Approval Response Producer - Kafka transactional producer para decisoes de aprovacao

Publica decisoes de aprovacao/rejeicao no topico de responses com semantica exactly-once.
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
from src.models.approval import ApprovalResponse

logger = structlog.get_logger()

# Schema Avro para ApprovalResponse
# cognitive_plan e serializado como JSON string para suportar estruturas aninhadas
APPROVAL_RESPONSE_SCHEMA = """
{
  "type": "record",
  "name": "ApprovalResponse",
  "namespace": "com.neuralhive.approval",
  "fields": [
    {"name": "plan_id", "type": "string"},
    {"name": "intent_id", "type": "string"},
    {"name": "decision", "type": {"type": "enum", "name": "Decision", "symbols": ["approved", "rejected"]}},
    {"name": "approved_by", "type": "string"},
    {"name": "approved_at", "type": "long"},
    {"name": "rejection_reason", "type": ["null", "string"], "default": null},
    {"name": "cognitive_plan_json", "type": ["null", "string"], "default": null, "doc": "JSON-serialized cognitive plan"}
  ]
}
"""


class ApprovalResponseProducer:
    """Kafka producer para responses de aprovacao"""

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
        return f'approval-response-producer-{hostname}-{pod_uid}'

    async def initialize(self):
        """Inicializa producer Kafka com suporte a transacoes"""
        producer_config = {
            'bootstrap.servers': self.settings.kafka_bootstrap_servers,
            'enable.idempotence': self.settings.kafka_enable_idempotence,
            'transactional.id': self._transactional_id,
            'acks': 'all',
            'max.in.flight.requests.per.connection': 5,
        }

        # Adiciona configuracao de seguranca
        if self.settings.kafka_security_protocol != 'PLAINTEXT':
            producer_config.update({
                'security.protocol': self.settings.kafka_security_protocol,
                'sasl.mechanism': self.settings.kafka_sasl_mechanism,
                'sasl.username': self.settings.kafka_sasl_username,
                'sasl.password': self.settings.kafka_sasl_password,
            })

        self.producer = Producer(producer_config)

        # Inicializa Schema Registry client (opcional para dev)
        if self.settings.schema_registry_url and self.settings.schema_registry_url.strip():
            logger.info(
                'Inicializando Schema Registry para approval response producer',
                url=self.settings.schema_registry_url
            )

            try:
                self.schema_registry_client = SchemaRegistryClient({
                    'url': self.settings.schema_registry_url
                })

                self.avro_serializer = AvroSerializer(
                    self.schema_registry_client,
                    APPROVAL_RESPONSE_SCHEMA
                )
                logger.info(
                    'Schema Registry habilitado para response producer',
                    url=self.settings.schema_registry_url
                )
            except Exception as e:
                logger.warning(
                    'Falha ao inicializar Schema Registry - usando JSON',
                    error=str(e)
                )
                self.avro_serializer = None
        else:
            logger.warning(
                'Schema Registry desabilitado - usando JSON',
                environment=self.settings.environment
            )

        # Inicializa transacoes
        self.producer.init_transactions()

        logger.info(
            'Approval Response Producer inicializado',
            transactional_id=self._transactional_id,
            topic=self.settings.kafka_approval_responses_topic
        )

    async def send_approval_response(
        self,
        response: ApprovalResponse,
        correlation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None
    ):
        """
        Envia decisao de aprovacao para Kafka

        Args:
            response: ApprovalResponse com a decisao
            correlation_id: ID de correlacao opcional
            trace_id: OpenTelemetry trace ID
            span_id: OpenTelemetry span ID
        """
        topic = self.settings.kafka_approval_responses_topic

        try:
            # Inicia transacao
            self.producer.begin_transaction()

            # Serializa response (Avro ou JSON)
            if self.avro_serializer:
                kafka_data = response.to_kafka_dict()
                serialization_context = SerializationContext(topic, MessageField.VALUE)
                value = self.avro_serializer(kafka_data, serialization_context)
                content_type = 'application/avro'
            else:
                value = json.dumps(
                    response.to_kafka_dict(),
                    default=str
                ).encode('utf-8')
                content_type = 'application/json'

            # Prepara headers
            headers = [
                ('plan-id', response.plan_id.encode('utf-8')),
                ('intent-id', response.intent_id.encode('utf-8')),
                ('decision', response.decision.encode('utf-8')),
                ('approved-by', response.approved_by.encode('utf-8')),
                ('content-type', content_type.encode('utf-8')),
            ]

            if correlation_id:
                headers.append(('correlation-id', correlation_id.encode('utf-8')))
            if trace_id:
                headers.append(('trace-id', trace_id.encode('utf-8')))
            if span_id:
                headers.append(('span-id', span_id.encode('utf-8')))

            # Partition key pelo plan_id
            key = response.plan_id.encode('utf-8')

            # Produz mensagem
            self.producer.produce(
                topic=topic,
                key=key,
                value=value,
                headers=headers,
                on_delivery=self._delivery_callback
            )

            # Flush
            self.producer.flush()

            # Commit transacao
            self.producer.commit_transaction()

            logger.info(
                'Approval response publicado',
                plan_id=response.plan_id,
                intent_id=response.intent_id,
                decision=response.decision,
                approved_by=response.approved_by,
                topic=topic,
                format=content_type
            )

        except Exception as e:
            logger.error(
                'Erro ao publicar approval response',
                plan_id=response.plan_id,
                error=str(e)
            )

            # Aborta transacao em caso de erro
            self.producer.abort_transaction()
            raise

    def _delivery_callback(self, err, msg):
        """Callback de entrega de mensagens"""
        if err:
            logger.error(
                'Falha na entrega do approval response',
                error=err,
                topic=msg.topic()
            )
        else:
            logger.debug(
                'Approval response entregue',
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset()
            )

    async def close(self):
        """Fecha producer gracefully"""
        if self.producer:
            self.producer.flush()
            logger.info('Approval Response Producer fechado')
