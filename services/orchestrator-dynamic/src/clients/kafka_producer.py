"""
Cliente Kafka Producer para publicação de Execution Tickets.
"""
import asyncio
import json
from pathlib import Path
from typing import Dict, Any, Optional
from time import perf_counter
from confluent_kafka import Producer, KafkaError
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
import structlog

logger = structlog.get_logger()


class KafkaProducerClient:
    """Producer Kafka para publicação de tickets no tópico execution.tickets."""

    def __init__(self, config, sasl_username_override=None, sasl_password_override=None):
        """
        Inicializa o producer Kafka.

        Args:
            config: Configurações da aplicação
            sasl_username_override: Username SASL override (ex: de Vault)
            sasl_password_override: Password SASL override (ex: de Vault)
        """
        self.config = config
        self.producer: Optional[Producer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_serializer: Optional[AvroSerializer] = None
        self.incident_avro_serializer: Optional[AvroSerializer] = None
        self.metrics = None
        self.sasl_username = sasl_username_override if sasl_username_override is not None else config.kafka_sasl_username
        self.sasl_password = sasl_password_override if sasl_password_override is not None else config.kafka_sasl_password

    async def initialize(self):
        """Inicializa o producer Kafka."""
        logger.info(
            'Inicializando Kafka producer',
            topic=self.config.kafka_tickets_topic,
            bootstrap_servers=self.config.kafka_bootstrap_servers
        )

        producer_config = {
            'bootstrap.servers': self.config.kafka_bootstrap_servers,
            'enable.idempotence': True,
            'acks': 'all',
            'compression.type': 'gzip'
        }

        producer_config.update(self._configure_security())
        self.producer = Producer(producer_config)

        try:
            self.schema_registry_client = SchemaRegistryClient({'url': self.config.kafka_schema_registry_url})

            # Serializer de Execution Tickets
            ticket_schema_path = Path(self.config.schemas_base_path) / 'execution-ticket' / 'execution-ticket.avsc'
            ticket_schema_str = ticket_schema_path.read_text()
            self.avro_serializer = AvroSerializer(self.schema_registry_client, ticket_schema_str)

            # Serializer de incidentes de orquestração (Fluxo E)
            incident_schema_path = Path(self.config.schemas_base_path) / 'orchestration-incident' / 'orchestration-incident.avsc'
            try:
                incident_schema_str = incident_schema_path.read_text()
                self.incident_avro_serializer = AvroSerializer(self.schema_registry_client, incident_schema_str)
            except Exception as incident_exc:
                logger.warning(
                    'incident_schema_unavailable_fallback_json',
                    error=str(incident_exc),
                    schema_path=str(incident_schema_path)
                )
                self.incident_avro_serializer = None

            logger.info('Schema Registry habilitado para producer', url=self.config.kafka_schema_registry_url)
        except Exception as exc:
            logger.warning(
                'Schema Registry indisponível - fallback para JSON',
                error=str(exc)
            )
            self.schema_registry_client = None
            self.avro_serializer = None
            self.incident_avro_serializer = None

        logger.info('Kafka producer inicializado com sucesso')

    async def publish_ticket(
        self,
        ticket: Dict[str, Any],
        topic: str = None
    ) -> Dict[str, Any]:
        """
        Publica um Execution Ticket no tópico Kafka.

        Args:
            ticket: Ticket de execução a ser publicado
            topic: Tópico Kafka (usa kafka_tickets_topic do config por padrão)

        Returns:
            Resultado da publicação contendo offset e metadata

        Raises:
            KafkaError: Em caso de falha na publicação
        """
        if not self.producer:
            raise RuntimeError('Producer não inicializado. Chame initialize() primeiro.')

        topic = topic or self.config.kafka_tickets_topic
        ticket_id = ticket['ticket_id']

        try:
            serialized_value = self._serialize_value(ticket, topic)
            key_bytes = ticket_id.encode('utf-8') if ticket_id else None

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._produce_sync(topic, serialized_value, key_bytes, ticket_id)
            )

            logger.info(
                'Ticket publicado com sucesso no Kafka',
                ticket_id=ticket_id,
                topic=result.get('topic'),
                partition=result.get('partition'),
                offset=result.get('offset')
            )

            return result

        except KafkaError as e:
            logger.error(
                'Erro ao publicar ticket no Kafka',
                ticket_id=ticket_id,
                topic=topic,
                error=str(e),
                exc_info=True
            )
            raise

    async def send(
        self,
        topic: str,
        value: Dict[str, Any],
        key: str = None
    ) -> Dict[str, Any]:
        """
        Publica uma mensagem genérica no tópico Kafka.

        Este método complementa publish_ticket() e permite publicação
        de eventos não-ticket (ex: allocation outcomes, métricas ML).

        Args:
            topic: Tópico Kafka
            value: Payload da mensagem (será serializado como JSON ou Avro)
            key: Chave da mensagem (opcional)

        Returns:
            Resultado da publicação contendo offset e metadata

        Raises:
            KafkaError: Em caso de falha na publicação
        """
        if not self.producer:
            raise RuntimeError('Producer não inicializado. Chame initialize() primeiro.')

        try:
            serialized_value = self._serialize_value(value, topic)
            key_bytes = key.encode('utf-8') if key else None

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._produce_sync(topic, serialized_value, key_bytes, key)
            )

            logger.debug(
                'Mensagem publicada com sucesso no Kafka',
                topic=result.get('topic'),
                partition=result.get('partition'),
                offset=result.get('offset'),
                key=key
            )

            return result

        except KafkaError as e:
            logger.error(
                'Erro ao publicar mensagem no Kafka',
                topic=topic,
                key=key,
                error=str(e),
                exc_info=True
            )
            raise

    async def publish_incident_avro(self, incident_event: Dict[str, Any]) -> bool:
        """
        Publica um incidente de orquestração (Fluxo E) usando Avro com Schema Registry.

        Fail-open: retorna False em caso de falha após retries.
        """
        if not self.producer:
            raise RuntimeError('Producer não inicializado. Chame initialize() primeiro.')

        topic = getattr(self.config, 'kafka_incidents_topic', 'orchestration.incidents')
        incident_id = incident_event.get('incident_id')
        incident_type = incident_event.get('incident_type', 'UNKNOWN')
        key = incident_id or incident_event.get('workflow_id')

        attempt = 0
        start_time = perf_counter()
        last_error: Optional[Exception] = None

        while attempt < 3:
            attempt += 1
            try:
                serialized_value = self._serialize_incident_value(incident_event, topic)
                key_bytes = key.encode('utf-8') if key else None

                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._produce_sync(topic, serialized_value, key_bytes, incident_id)
                )

                duration = perf_counter() - start_time
                self._record_incident_metrics(success=True, duration_seconds=duration, incident_type=incident_type)
                logger.info(
                    'self_healing.incident_published',
                    incident_id=incident_id,
                    workflow_id=incident_event.get('workflow_id'),
                    incident_type=incident_type,
                    playbook=incident_event.get('recommended_playbook'),
                    duration_seconds=round(duration, 4)
                )
                return True
            except Exception as exc:
                last_error = exc
                duration = perf_counter() - start_time
                self._record_incident_metrics(success=False, duration_seconds=duration, incident_type=incident_type)

                if attempt >= 3:
                    logger.warning(
                        'self_healing.kafka_publish_failed',
                        workflow_id=incident_event.get('workflow_id'),
                        incident_id=incident_id,
                        incident_type=incident_type,
                        error=str(exc),
                        retry_count=attempt
                    )
                    break

                sleep_seconds = min(10, 2 ** attempt)
                logger.warning(
                    'self_healing.incident_publish_retry',
                    incident_id=incident_id,
                    workflow_id=incident_event.get('workflow_id'),
                    incident_type=incident_type,
                    retry_count=attempt,
                    sleep_seconds=sleep_seconds,
                    error=str(exc)
                )
                await asyncio.sleep(sleep_seconds)

        if last_error:
            logger.error(
                'self_healing.incident_buffered',
                incident_id=incident_id,
                workflow_id=incident_event.get('workflow_id'),
                incident_type=incident_type,
                error=str(last_error)
            )

        return False

    async def close(self):
        """Fecha o producer Kafka gracefully."""
        if self.producer:
            await asyncio.get_event_loop().run_in_executor(None, self.producer.flush)
            logger.info('Kafka producer fechado')

    def _serialize_value(self, value: Dict[str, Any], topic: str) -> bytes:
        """Serializa o payload usando Avro se disponível, caso contrário JSON."""
        if self.avro_serializer:
            context = SerializationContext(topic, MessageField.VALUE)
            return self.avro_serializer(value, context)

        return json.dumps(value).encode('utf-8')

    def _serialize_incident_value(self, value: Dict[str, Any], topic: str) -> bytes:
        """Serializa incidentes usando schema dedicado ou faz fallback para JSON."""
        if self.incident_avro_serializer:
            context = SerializationContext(topic, MessageField.VALUE)
            return self.incident_avro_serializer(value, context)

        return json.dumps(value).encode('utf-8')

    def _produce_sync(self, topic: str, value: bytes, key: Optional[bytes], ticket_id: Optional[str] = None) -> Dict[str, Any]:
        """Publica mensagem de forma síncrona e retorna metadata."""
        delivery_result: Dict[str, Any] = {}

        def callback(err, msg):
            self._delivery_callback(err, msg, ticket_id)
            delivery_result['error'] = err
            delivery_result['message'] = msg

        self.producer.produce(topic=topic, key=key, value=value, on_delivery=callback)
        self.producer.flush()

        if delivery_result.get('error'):
            raise delivery_result['error']

        msg = delivery_result.get('message')
        if msg:
            return {
                'published': True,
                'ticket_id': ticket_id,
                'topic': msg.topic(),
                'partition': msg.partition(),
                'offset': msg.offset(),
                'timestamp': msg.timestamp()[1]
            }

        return {'published': True, 'ticket_id': ticket_id, 'topic': topic}

    def _delivery_callback(self, err, msg, ticket_id: Optional[str]):
        """Callback de entrega para logging."""
        if err:
            logger.error(
                'Falha na entrega da mensagem Kafka',
                ticket_id=ticket_id,
                topic=msg.topic() if msg else None,
                error=str(err)
            )
        else:
            logger.debug(
                'Mensagem entregue no Kafka',
                ticket_id=ticket_id,
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset()
            )

    def _configure_security(self) -> Dict[str, Any]:
        """Configura parâmetros de segurança Kafka (SASL/SSL)."""
        security_config: Dict[str, Any] = {
            'security.protocol': self.config.kafka_security_protocol
        }

        if self.config.kafka_security_protocol in ['SASL_SSL', 'SASL_PLAINTEXT']:
            if getattr(self.config, 'kafka_sasl_mechanism', None):
                security_config['sasl.mechanism'] = self.config.kafka_sasl_mechanism
            if self.sasl_username and self.sasl_password:
                security_config['sasl.username'] = self.sasl_username
                security_config['sasl.password'] = self.sasl_password

        if self.config.kafka_security_protocol in ['SSL', 'SASL_SSL']:
            if getattr(self.config, 'kafka_ssl_ca_location', None):
                security_config['ssl.ca.location'] = self.config.kafka_ssl_ca_location
            if getattr(self.config, 'kafka_ssl_certificate_location', None):
                security_config['ssl.certificate.location'] = self.config.kafka_ssl_certificate_location
            if getattr(self.config, 'kafka_ssl_key_location', None):
                security_config['ssl.key.location'] = self.config.kafka_ssl_key_location

        return security_config

    def _record_incident_metrics(self, success: bool, duration_seconds: Optional[float], incident_type: str):
        """Registra métricas de publicação de incidentes (fail-open)."""
        metrics = self._get_metrics()
        if not metrics:
            return

        try:
            metrics.record_incident_publish(
                incident_type=incident_type,
                success=success,
                duration_seconds=duration_seconds or 0
            )
        except Exception as exc:
            logger.warning('incident_metrics_record_failed', error=str(exc))

    def _get_metrics(self):
        """Inicializa métricas Prometheus sob demanda (fail-open)."""
        if self.metrics is not None:
            return self.metrics

        try:
            from src.observability.metrics import get_metrics

            self.metrics = get_metrics()
        except Exception as exc:
            logger.warning('metrics_unavailable_incident_publish', error=str(exc))
            self.metrics = None

        return self.metrics
