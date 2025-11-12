"""Producer Kafka transacional para exactly-once delivery"""
import asyncio
import json
import os
import socket
from typing import Optional, Dict, Any
from confluent_kafka import Producer, KafkaError
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
import structlog

from models.intent_envelope import IntentEnvelope
from observability.metrics import message_size_histogram, message_size_gauge, record_too_large_counter
from config.settings import get_settings

logger = structlog.get_logger()

class KafkaIntentProducer:
    def __init__(self, bootstrap_servers: str = None, schema_registry_url: str = None):
        self.settings = get_settings()
        self.bootstrap_servers = bootstrap_servers or self.settings.kafka_bootstrap_servers
        self.schema_registry_url = schema_registry_url or self.settings.schema_registry_url
        self.producer: Optional[Producer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_serializer: Optional[AvroSerializer] = None
        self._ready = False
        self._transactional_id = self._generate_stable_transactional_id()
        self._cluster_metadata = None

    def _generate_stable_transactional_id(self) -> str:
        """Generate stable transactional ID per process/pod"""
        # Use environment variables for stability across restarts
        hostname = os.getenv('HOSTNAME', socket.gethostname())
        pod_uid = os.getenv('POD_UID', os.getenv('CONTAINER_ID', 'default'))

        # Truncate to ensure compatibility with Kafka limits (255 chars max)
        transactional_id = f"gateway-intencoes-{hostname}-{pod_uid}"[:200]

        logger.info(
            "Generated stable transactional ID",
            transactional_id=transactional_id,
            hostname=hostname,
            pod_uid=pod_uid
        )

        return transactional_id

    def _configure_security(self) -> Dict[str, Any]:
        """Configurar autenticação e SSL para Kafka"""
        security_config = {}

        # Configurar protocolo de segurança
        security_config['security.protocol'] = self.settings.kafka_security_protocol

        # Configurar SASL se necessário
        if self.settings.kafka_security_protocol in ['SASL_SSL', 'SASL_PLAINTEXT']:
            security_config['sasl.mechanism'] = self.settings.kafka_sasl_mechanism

            if self.settings.kafka_sasl_username and self.settings.kafka_sasl_password:
                security_config['sasl.username'] = self.settings.kafka_sasl_username
                security_config['sasl.password'] = self.settings.kafka_sasl_password

        # Configurar SSL se necessário
        if self.settings.kafka_security_protocol in ['SSL', 'SASL_SSL']:
            if self.settings.kafka_ssl_ca_location:
                security_config['ssl.ca.location'] = self.settings.kafka_ssl_ca_location

            if self.settings.kafka_ssl_certificate_location:
                security_config['ssl.certificate.location'] = self.settings.kafka_ssl_certificate_location

            if self.settings.kafka_ssl_key_location:
                security_config['ssl.key.location'] = self.settings.kafka_ssl_key_location

        logger.info(
            "Configuração de segurança aplicada",
            security_protocol=self.settings.kafka_security_protocol,
            sasl_mechanism=self.settings.kafka_sasl_mechanism,
            ssl_enabled=self.settings.kafka_security_protocol in ['SSL', 'SASL_SSL']
        )

        return security_config

    async def initialize(self):
        """Inicializar producer e schema registry"""
        try:
            # Configuração básica do producer com exactly-once
            producer_config = {
                'bootstrap.servers': self.bootstrap_servers,
                'enable.idempotence': True,
                'acks': 'all',
                'retries': 2147483647,  # MAX_INT
                'max.in.flight.requests.per.connection': 5,
                'transactional.id': self._transactional_id,
                'compression.type': self.settings.kafka_compression_type,
                'batch.size': self.settings.kafka_batch_size,
                'linger.ms': self.settings.kafka_linger_ms,
                'transaction.timeout.ms': 300000,  # 5 minutes - must be >= delivery.timeout.ms
                'delivery.timeout.ms': 120000,  # 2 minutes
                'request.timeout.ms': 30000,    # 30 seconds
                'message.max.bytes': 4194304    # 4MB to match broker settings
            }

            # Aplicar configurações de segurança
            security_config = self._configure_security()
            producer_config.update(security_config)

            self.producer = Producer(producer_config)

            # Schema Registry client (opcional para dev local)
            if self.schema_registry_url and self.schema_registry_url.strip():
                self.schema_registry_client = SchemaRegistryClient({'url': self.schema_registry_url})

                # Carregar schema Avro
                with open('/app/schemas/intent-envelope.avsc', 'r') as f:
                    schema_str = f.read()

                self.avro_serializer = AvroSerializer(
                    self.schema_registry_client,
                    schema_str
                )
                logger.info("Schema Registry habilitado", url=self.schema_registry_url)
            else:
                logger.warning("Schema Registry desabilitado - usando serialização JSON para dev local")
                self.schema_registry_client = None
                self.avro_serializer = None

            # Inicializar transações
            self.producer.init_transactions()
            self._ready = True

            logger.info("Producer Kafka inicializado com sucesso")

        except Exception as e:
            logger.error("Erro inicializando producer Kafka", error=str(e))
            raise

    async def get_cluster_metadata(self) -> Dict[str, Any]:
        """Obter metadados do cluster Kafka"""
        if not self.producer:
            raise RuntimeError("Producer não inicializado")

        try:
            metadata = self.producer.list_topics(timeout=10)

            brokers = []
            for broker in metadata.brokers.values():
                brokers.append({
                    "id": broker.id,
                    "host": broker.host,
                    "port": broker.port
                })

            topics = []
            for topic_name, topic_metadata in metadata.topics.items():
                partitions = []
                for partition in topic_metadata.partitions.values():
                    partitions.append({
                        "id": partition.id,
                        "leader": partition.leader,
                        "replicas": list(partition.replicas),
                        "isrs": list(partition.isrs)
                    })

                topics.append({
                    "name": topic_name,
                    "partitions": partitions,
                    "error": topic_metadata.error
                })

            return {
                "cluster_id": metadata.cluster_id,
                "controller_id": metadata.controller_id,
                "brokers": brokers,
                "topics": topics,
                "broker_count": len(brokers),
                "topic_count": len(topics)
            }

        except Exception as e:
            logger.error("Erro obtendo metadados do cluster", error=str(e))
            return {"error": str(e)}

    def is_ready(self) -> bool:
        return self._ready and self.producer is not None

    async def send_intent(
        self,
        intent_envelope: IntentEnvelope,
        topic_override: Optional[str] = None,
        confidence_status: Optional[str] = None,
        requires_validation: Optional[bool] = None,
        adaptive_threshold_used: Optional[bool] = None
    ):
        """Enviar intenção para Kafka com exactly-once e metadata de confiança"""
        logger.info(
            "🚀 send_intent CHAMADO",
            intent_id=intent_envelope.id,
            domain=intent_envelope.intent.domain.value,
            confidence=intent_envelope.confidence,
            confidence_status=confidence_status
        )

        if not self.is_ready():
            raise RuntimeError("Producer Kafka não inicializado")

        topic = topic_override or f"intentions.{intent_envelope.intent.domain.value}"
        partition_key = intent_envelope.get_partition_key()
        idempotency_key = intent_envelope.get_idempotency_key()

        logger.info(
            "📬 Preparando publicação",
            intent_id=intent_envelope.id,
            topic=topic,
            partition_key=partition_key
        )

        message_size = 0  # Initialize for error handling
        domain_str = intent_envelope.intent.domain.value

        try:
            # Iniciar transação
            self.producer.begin_transaction()
            logger.debug(f"Transação iniciada para intent_id={intent_envelope.id}, topic={topic}")

            # Serializar (Avro ou JSON)
            if self.avro_serializer:
                avro_data = intent_envelope.to_avro_dict()
                serialization_context = SerializationContext(topic, MessageField.VALUE)
                serialized_value = self.avro_serializer(avro_data, serialization_context)
                content_type = 'application/avro'
            else:
                # Fallback para JSON quando Schema Registry não disponível
                avro_data = intent_envelope.to_avro_dict()
                serialized_value = json.dumps(avro_data, ensure_ascii=False).encode('utf-8')
                content_type = 'application/json'

            # Measure message size and emit metrics
            message_size = len(serialized_value)

            message_size_histogram.labels(domain=domain_str).observe(message_size)
            message_size_gauge.set(message_size)

            # Check for size warning (90% of 4MB limit)
            size_limit_warning = 3670016  # 3.5MB
            if message_size > size_limit_warning:
                logger.warning(
                    "Large envelope size approaching limit",
                    intent_id=intent_envelope.id,
                    domain=domain_str,
                    message_size_bytes=message_size,
                    size_limit_bytes=4194304
                )

            # Headers para metadados e auditoria
            headers = {
                'intent-id': intent_envelope.id.encode('utf-8'),
                'correlation-id': (intent_envelope.correlation_id or '').encode('utf-8'),
                'idempotency-key': idempotency_key.encode('utf-8'),
                'schema-version': '1.0.0'.encode('utf-8'),
                'content-type': content_type.encode('utf-8'),
                'message-size': str(message_size).encode('utf-8'),
                'source-ip': os.getenv('SOURCE_IP', 'unknown').encode('utf-8'),
                'user-id': (intent_envelope.actor.id if intent_envelope.actor else 'anonymous').encode('utf-8'),
                'timestamp': str(int(asyncio.get_event_loop().time() * 1000)).encode('utf-8'),
                'producer-id': self._transactional_id.encode('utf-8'),
                'confidence-score': str(intent_envelope.confidence).encode('utf-8'),
                'confidence-status': (confidence_status or 'unknown').encode('utf-8'),
                'requires-validation': str(requires_validation if requires_validation is not None else False).encode('utf-8'),
                'adaptive-threshold-used': str(adaptive_threshold_used if adaptive_threshold_used is not None else False).encode('utf-8')
            }

            # Produzir mensagem
            future = self.producer.produce(
                topic=topic,
                key=partition_key.encode('utf-8'),
                value=serialized_value,
                headers=headers,
                callback=self._delivery_callback
            )

            # Flush para garantir envio
            self.producer.flush(timeout=10.0)
            logger.debug(f"Flush realizado para intent_id={intent_envelope.id}")

            # Commit da transação
            self.producer.commit_transaction()
            logger.debug(f"Transação commitada para intent_id={intent_envelope.id}")

            logger.info(
                "Intenção enviada para Kafka",
                intent_id=intent_envelope.id,
                topic=topic,
                partition_key=partition_key,
                idempotency_key=idempotency_key,
                confidence=intent_envelope.confidence,
                confidence_status=confidence_status,
                requires_validation=requires_validation
            )

        except Exception as e:
            error_str = str(e)

            # Handle specific RECORD_TOO_LARGE errors
            if "RECORD_TOO_LARGE" in error_str or "message size" in error_str.lower():
                record_too_large_counter.labels(domain=domain_str).inc()

                logger.error(
                    "Intenção rejeitada por exceder limite de tamanho",
                    intent_id=intent_envelope.id,
                    domain=domain_str,
                    message_size_bytes=message_size,
                    error=error_str
                )

                # Tentar enviar para DLQ se configurado
                await self.send_to_dlq(intent_envelope, error_str, message_size)

            else:
                logger.error(
                    "Erro enviando intenção para Kafka",
                    intent_id=intent_envelope.id,
                    domain=domain_str,
                    error=error_str
                )

            # Abort da transação em caso de erro
            try:
                self.producer.abort_transaction()
            except:
                pass
            raise

    def _delivery_callback(self, err, msg):
        """Callback de entrega da mensagem"""
        if err:
            logger.error("Erro na entrega da mensagem", error=str(err))
        else:
            logger.debug(
                "Mensagem entregue",
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset()
            )

    async def close(self):
        """Fechar producer"""
        if self.producer:
            try:
                self.producer.flush(timeout=30.0)
                self.producer = None
                self._ready = False
                logger.info("Producer Kafka fechado")
            except Exception as e:
                logger.error("Erro fechando producer", error=str(e))

    async def send_to_dlq(self, intent_envelope: IntentEnvelope, error_reason: str, original_message_size: int = 0):
        """Enviar mensagem com falha para Dead Letter Queue"""
        try:
            dlq_topic = f"dlq.intentions.{intent_envelope.intent.domain.value}"

            # Criar envelope de erro para DLQ
            dlq_envelope = {
                "original_intent_id": intent_envelope.id,
                "error_reason": error_reason,
                "error_timestamp": int(asyncio.get_event_loop().time() * 1000),
                "original_domain": intent_envelope.intent.domain.value,
                "original_message_size": original_message_size,
                "retry_count": 0,  # Inicializar como 0 na primeira vez que entra na DLQ
                "original_intent": intent_envelope.to_avro_dict()
            }

            # Headers para DLQ
            dlq_headers = {
                'error-reason': error_reason.encode('utf-8'),
                'original-intent-id': intent_envelope.id.encode('utf-8'),
                'dlq-timestamp': str(int(asyncio.get_event_loop().time() * 1000)).encode('utf-8'),
                'content-type': 'application/json'.encode('utf-8')
            }

            # Enviar para DLQ (sem transação para evitar conflitos)
            self.producer.produce(
                topic=dlq_topic,
                key=intent_envelope.id.encode('utf-8'),
                value=json.dumps(dlq_envelope, ensure_ascii=False).encode('utf-8'),
                headers=dlq_headers
            )

            # Flush para garantir entrega da DLQ
            self.producer.flush(timeout=5.0)

            logger.info(
                "Mensagem enviada para DLQ",
                intent_id=intent_envelope.id,
                dlq_topic=dlq_topic,
                error_reason=error_reason
            )

        except Exception as dlq_error:
            logger.error(
                "Erro enviando para DLQ",
                intent_id=intent_envelope.id,
                dlq_error=str(dlq_error),
                original_error=error_reason
            )