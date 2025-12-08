import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import structlog
from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext

logger = structlog.get_logger()


class KafkaResultProducer:
    '''Producer Kafka para tópico execution.results'''

    def __init__(
        self,
        config,
        sasl_username_override: Optional[str] = None,
        sasl_password_override: Optional[str] = None
    ):
        self.config = config
        self.logger = logger.bind(service='kafka_result_producer')
        self.producer: Optional[Producer] = None
        self.schema_registry_client: Optional[SchemaRegistryClient] = None
        self.avro_serializer: Optional[AvroSerializer] = None
        self.sasl_username_override = sasl_username_override
        self.sasl_password_override = sasl_password_override

    async def initialize(self):
        '''Inicializar producer Kafka'''
        try:
            producer_config = {
                'bootstrap.servers': self.config.kafka_bootstrap_servers,
                'acks': 'all',
                'retries': 3,
                'enable.idempotence': True,
                'max.in.flight.requests.per.connection': 1
            }
            producer_config.update(self._configure_security())

            self.producer = Producer(producer_config)

            try:
                schema_path = Path(self.config.schemas_base_path) / 'execution-result' / 'execution-result.avsc'
                schema_str = schema_path.read_text()

                self.schema_registry_client = SchemaRegistryClient(
                    {'url': self.config.kafka_schema_registry_url}
                )
                self.avro_serializer = AvroSerializer(self.schema_registry_client, schema_str)
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
                self.avro_serializer = None

            self.logger.info(
                'kafka_producer_initialized',
                topic=self.config.kafka_results_topic
            )

            # TODO: Incrementar métrica worker_agent_kafka_producer_initialized_total

        except Exception as e:
            self.logger.error('kafka_producer_init_failed', error=str(e))
            raise

    async def publish_result(
        self,
        ticket_id: str,
        status: str,
        result: Dict[str, Any],
        error_message: Optional[str] = None,
        actual_duration_ms: Optional[int] = None
    ) -> Dict[str, Any]:
        '''Publicar resultado no Kafka'''
        try:
            payload = {
                'ticket_id': ticket_id,
                'status': status,
                'result': self._normalize_result(result),
                'error_message': error_message,
                'actual_duration_ms': actual_duration_ms,
                'agent_id': self.config.agent_id,
                'timestamp': int(datetime.now().timestamp() * 1000),
                'schema_version': 1
            }

            topic = self.config.kafka_results_topic
            serialization_context = SerializationContext(topic, MessageField.VALUE)

            if self.avro_serializer:
                value = self.avro_serializer(payload, serialization_context)
            else:
                value = json.dumps(payload).encode('utf-8')

            key = ticket_id.encode('utf-8')
            loop = asyncio.get_running_loop()
            delivery_future: asyncio.Future = loop.create_future()

            def _delivery_callback(err, msg):
                if err:
                    loop.call_soon_threadsafe(
                        delivery_future.set_exception,
                        RuntimeError(f'Failed to deliver message: {err}')
                    )
                else:
                    loop.call_soon_threadsafe(delivery_future.set_result, msg)

            def _produce():
                self.producer.produce(
                    topic=topic,
                    key=key,
                    value=value,
                    on_delivery=_delivery_callback
                )
                self.producer.poll(0)

            await loop.run_in_executor(None, _produce)
            msg = await delivery_future
            await loop.run_in_executor(None, self.producer.flush)

            self.logger.info(
                'result_published',
                ticket_id=ticket_id,
                status=status,
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset()
            )

            # TODO: Incrementar métrica worker_agent_results_published_total{status=...}

            return {
                'topic': msg.topic(),
                'partition': msg.partition(),
                'offset': msg.offset()
            }

        except Exception as e:
            self.logger.error(
                'publish_result_failed',
                ticket_id=ticket_id,
                status=status,
                error=str(e)
            )
            # TODO: Incrementar métrica worker_agent_kafka_producer_errors_total
            raise

    async def stop(self):
        '''Parar producer'''
        if self.producer:
            await asyncio.get_event_loop().run_in_executor(None, self.producer.flush)
            self.logger.info('kafka_producer_stopped')

    def _normalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        '''Normaliza payload para schema Avro (maps string)'''
        normalized = dict(result or {})
        if 'success' not in normalized:
            raise ValueError('Execution result missing required field: success')
        output = normalized.get('output', {}) or {}
        metadata = normalized.get('metadata', {}) or {}
        normalized['output'] = {k: str(v) for k, v in output.items()}
        normalized['metadata'] = {k: str(v) for k, v in metadata.items()}
        logs = normalized.get('logs', [])
        normalized['logs'] = [str(item) for item in logs] if isinstance(logs, list) else []
        return normalized

    def _configure_security(self) -> dict:
        """Configuração de segurança Kafka (SASL/SSL)."""
        security_config = {
            'security.protocol': self.config.kafka_security_protocol
        }

        if self.config.kafka_security_protocol in ['SASL_SSL', 'SASL_PLAINTEXT']:
            if getattr(self.config, 'kafka_sasl_mechanism', None):
                security_config['sasl.mechanism'] = self.config.kafka_sasl_mechanism
            username = self.sasl_username_override or self.config.kafka_sasl_username
            password = self.sasl_password_override or self.config.kafka_sasl_password
            if username and password:
                security_config['sasl.username'] = username
                security_config['sasl.password'] = password

        if self.config.kafka_security_protocol in ['SSL', 'SASL_SSL']:
            if getattr(self.config, 'kafka_ssl_ca_location', None):
                security_config['ssl.ca.location'] = self.config.kafka_ssl_ca_location
            if getattr(self.config, 'kafka_ssl_certificate_location', None):
                security_config['ssl.certificate.location'] = self.config.kafka_ssl_certificate_location
            if getattr(self.config, 'kafka_ssl_key_location', None):
                security_config['ssl.key.location'] = self.config.kafka_ssl_key_location

        return security_config
