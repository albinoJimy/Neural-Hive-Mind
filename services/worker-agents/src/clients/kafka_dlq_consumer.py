import asyncio
import json
import structlog
from confluent_kafka import Consumer, KafkaError
from typing import Optional
from datetime import datetime

logger = structlog.get_logger()


class KafkaDLQConsumer:
    '''Consumer para Dead Letter Queue - alerta SRE e persiste no MongoDB'''

    def __init__(self, config, mongodb_client=None, alert_manager=None, metrics=None):
        self.config = config
        self.mongodb_client = mongodb_client
        self.alert_manager = alert_manager
        self.metrics = metrics
        self.logger = logger.bind(service='kafka_dlq_consumer')
        self.consumer: Optional[Consumer] = None
        self.running = False

    def _configure_security(self) -> dict:
        """Configuracao de seguranca Kafka (SASL/SSL)."""
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

    async def initialize(self):
        '''Inicializar consumer DLQ'''
        try:
            consumer_config = {
                'bootstrap.servers': self.config.kafka_bootstrap_servers,
                'group.id': f"{self.config.kafka_consumer_group_id}-dlq",
                'auto.offset.reset': 'earliest',  # Processar todas as mensagens DLQ
                'enable.auto.commit': True,  # Auto-commit para DLQ (ja processado)
                'auto.commit.interval.ms': 5000
            }

            # Adicionar configuracao de seguranca
            consumer_config.update(self._configure_security())

            self.consumer = Consumer(consumer_config)

            dlq_topic = getattr(self.config, 'kafka_dlq_topic', 'execution.tickets.dlq')
            self.consumer.subscribe([dlq_topic])

            self.logger.info(
                'kafka_dlq_consumer_initialized',
                topic=dlq_topic,
                group_id=consumer_config['group.id']
            )

        except Exception as e:
            self.logger.error('kafka_dlq_consumer_init_failed', error=str(e))
            raise

    async def start(self):
        '''Iniciar loop de consumo DLQ'''
        self.running = True

        try:
            while self.running:
                message = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.consumer.poll(timeout=1.0)
                )

                if message is None:
                    continue

                if message.error():
                    if message.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    raise message.error()

                if not self.running:
                    break

                try:
                    # Deserializar mensagem DLQ
                    dlq_message = json.loads(message.value().decode('utf-8'))

                    ticket_id = dlq_message.get('ticket_id', 'unknown')
                    task_type = dlq_message.get('task_type', 'unknown')
                    dlq_metadata = dlq_message.get('dlq_metadata', {})

                    self.logger.warning(
                        'dlq_message_received',
                        ticket_id=ticket_id,
                        task_type=task_type,
                        retry_count=dlq_metadata.get('retry_count'),
                        error=dlq_metadata.get('original_error')
                    )

                    # Persistir no MongoDB
                    await self._persist_dlq_message(dlq_message)

                    # Alertar SRE
                    await self._alert_sre(dlq_message)

                except Exception as e:
                    self.logger.error(
                        'dlq_message_processing_failed',
                        error=str(e),
                        exc_info=True
                    )
                    # Nao propagar - auto-commit garantira que nao reprocessamos

        except Exception as e:
            self.logger.error('kafka_dlq_consumer_loop_failed', error=str(e))
            raise
        finally:
            self.running = False

    async def _persist_dlq_message(self, dlq_message: dict):
        '''Persistir mensagem DLQ no MongoDB para analise forense'''
        if not self.mongodb_client:
            self.logger.warning('mongodb_client_not_available_skipping_persistence')
            return

        try:
            collection = self.mongodb_client.db['execution_tickets_dlq']

            document = {
                **dlq_message,
                'processed_at': datetime.now(),
                'processed_at_ms': int(datetime.now().timestamp() * 1000)
            }

            await collection.insert_one(document)

            self.logger.info(
                'dlq_message_persisted',
                ticket_id=dlq_message.get('ticket_id')
            )

        except Exception as e:
            self.logger.error(
                'dlq_persistence_failed',
                ticket_id=dlq_message.get('ticket_id'),
                error=str(e)
            )

    async def _alert_sre(self, dlq_message: dict):
        '''Enviar alerta para SRE sobre mensagem no DLQ'''
        try:
            ticket_id = dlq_message.get('ticket_id', 'unknown')
            task_type = dlq_message.get('task_type', 'unknown')
            dlq_metadata = dlq_message.get('dlq_metadata', {})

            alert_payload = {
                'severity': 'warning',
                'component': 'worker-agents',
                'alert_type': 'dlq_message',
                'ticket_id': ticket_id,
                'task_type': task_type,
                'retry_count': dlq_metadata.get('retry_count'),
                'error': dlq_metadata.get('original_error'),
                'message': f'Execution ticket {ticket_id} enviado para DLQ apos {dlq_metadata.get("retry_count")} tentativas',
                'runbook_url': 'https://docs.neural-hive.io/runbooks/dlq-ticket-recovery'
            }

            if self.alert_manager:
                await self.alert_manager.send_alert(alert_payload)

            self.logger.info('sre_alert_sent', ticket_id=ticket_id)

        except Exception as e:
            self.logger.error(
                'sre_alert_failed',
                ticket_id=dlq_message.get('ticket_id'),
                error=str(e)
            )

    async def stop(self):
        '''Parar consumer DLQ'''
        self.running = False
        if self.consumer:
            await asyncio.get_event_loop().run_in_executor(None, self.consumer.close)
            self.logger.info('kafka_dlq_consumer_stopped')
