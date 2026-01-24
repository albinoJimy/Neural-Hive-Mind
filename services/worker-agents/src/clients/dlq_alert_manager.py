"""
DLQ Alert Manager - Gerenciamento de alertas para mensagens no DLQ.

Responsável por enviar alertas para SRE quando tickets falham definitivamente.
"""
import json
import uuid
from datetime import datetime
from typing import Dict, Optional

import structlog
from confluent_kafka import Producer

logger = structlog.get_logger()


class DLQAlertManager:
    """
    Gerenciador de alertas para mensagens no Dead Letter Queue.

    Envia alertas via Kafka para o tópico de alertas SRE quando
    tickets são enviados para o DLQ após esgotar todas as tentativas.
    """

    def __init__(self, config, metrics=None):
        """
        Inicializar DLQ Alert Manager.

        Args:
            config: Configurações do worker-agents (WorkerAgentSettings)
            metrics: Instância de métricas (opcional)
        """
        self.config = config
        self.metrics = metrics
        self.producer: Optional[Producer] = None
        self.logger = logger.bind(service='dlq_alert_manager')

    def _configure_security(self) -> dict:
        """Configuração de segurança Kafka (SASL/SSL)."""
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
        """Inicializar producer Kafka para alertas."""
        try:
            producer_config = {
                'bootstrap.servers': self.config.kafka_bootstrap_servers,
                'acks': 'all',
                'retries': 3,
                'enable.idempotence': True
            }
            producer_config.update(self._configure_security())

            self.producer = Producer(producer_config)

            self.logger.info(
                'dlq_alert_manager_initialized',
                alert_topic=self.config.dlq_alert_kafka_topic
            )

        except Exception as e:
            self.logger.error('dlq_alert_manager_init_failed', error=str(e))
            raise

    async def send_alert(self, alert_payload: Dict) -> bool:
        """
        Enviar alerta para SRE via Kafka.

        Args:
            alert_payload: Payload do alerta com informações do ticket DLQ

        Returns:
            bool: True se alerta foi enviado, False caso contrário
        """
        if not self.producer:
            self.logger.warning('alert_producer_not_initialized')
            return False

        if not getattr(self.config, 'dlq_alert_enabled', True):
            self.logger.debug('dlq_alerts_disabled')
            return False

        try:
            ticket_id = alert_payload.get('ticket_id', 'unknown')
            task_type = alert_payload.get('task_type', 'unknown')

            # Construir evento de alerta estruturado
            alert_event = {
                'alert_id': str(uuid.uuid4()),
                'event_type': 'DLQ_ALERT',
                'severity': alert_payload.get('severity', 'warning'),
                'component': 'worker-agents',
                'alert_type': 'dlq_message',
                'ticket_id': ticket_id,
                'task_type': task_type,
                'retry_count': alert_payload.get('retry_count'),
                'error': alert_payload.get('error'),
                'message': alert_payload.get(
                    'message',
                    f'Execution ticket {ticket_id} enviado para DLQ apos {alert_payload.get("retry_count")} tentativas'
                ),
                'runbook_url': 'https://docs.neural-hive.io/runbooks/dlq-ticket-recovery',
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'metadata': {
                    'plan_id': alert_payload.get('plan_id'),
                    'workflow_id': alert_payload.get('workflow_id'),
                    'error_type': alert_payload.get('error_type')
                }
            }

            # Publicar no tópico de alertas
            topic = self.config.dlq_alert_kafka_topic
            message_value = json.dumps(alert_event).encode('utf-8')

            delivery_result = {'success': False}

            def delivery_callback(err, msg):
                if err:
                    self.logger.error(
                        'dlq_alert_delivery_failed',
                        ticket_id=ticket_id,
                        error=str(err)
                    )
                else:
                    delivery_result['success'] = True

            self.producer.produce(
                topic=topic,
                key=alert_event['alert_id'].encode('utf-8'),
                value=message_value,
                callback=delivery_callback
            )

            self.producer.flush(timeout=5)

            if delivery_result['success']:
                self.logger.info(
                    'dlq_alert_sent',
                    alert_id=alert_event['alert_id'],
                    ticket_id=ticket_id,
                    severity=alert_event['severity']
                )

                if self.metrics:
                    self.metrics.dlq_alerts_sent_total.labels(
                        severity=alert_event['severity'],
                        task_type=task_type
                    ).inc()

                return True
            else:
                return False

        except Exception as e:
            self.logger.error(
                'dlq_alert_failed',
                ticket_id=alert_payload.get('ticket_id'),
                error=str(e)
            )
            return False

    async def close(self):
        """Fechar producer de alertas."""
        if self.producer:
            self.producer.flush(timeout=5)
            self.logger.info('dlq_alert_manager_closed')
