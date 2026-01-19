"""
Rejection Notifier - Produtor Kafka para notificações de rejeição de planos

Responsável por notificar consumidores sobre planos cognitivos que foram
rejeitados pelo fluxo de aprovação.
"""

import os
import structlog
import json
from typing import Optional
from confluent_kafka import Producer

from src.config.settings import Settings

logger = structlog.get_logger()


class RejectionNotifier:
    """
    Notificador de rejeições de planos cognitivos.

    Publica notificações no tópico de rejeições para que sistemas
    downstream possam reagir a planos rejeitados (ex: notificar usuário,
    atualizar UI, disparar workflows alternativos).
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.producer: Optional[Producer] = None
        self._transactional_id = self._generate_transactional_id()

    def _generate_transactional_id(self) -> str:
        """Gera ID transacional estável por pod"""
        hostname = os.environ.get('HOSTNAME', 'local')
        pod_uid = os.environ.get('POD_UID', '0')
        return f'rejection-notifier-{hostname}-{pod_uid}'

    async def initialize(self):
        """Inicializa producer Kafka"""
        producer_config = {
            'bootstrap.servers': self.settings.kafka_bootstrap_servers,
            'enable.idempotence': self.settings.kafka_enable_idempotence,
            'transactional.id': self._transactional_id,
            'acks': 'all',
            'max.in.flight.requests.per.connection': 5,
        }

        # Configuração de segurança
        if self.settings.kafka_security_protocol != 'PLAINTEXT':
            producer_config.update({
                'security.protocol': self.settings.kafka_security_protocol,
                'sasl.mechanism': self.settings.kafka_sasl_mechanism,
                'sasl.username': self.settings.kafka_sasl_username,
                'sasl.password': self.settings.kafka_sasl_password,
            })

        self.producer = Producer(producer_config)
        self.producer.init_transactions()

        logger.info(
            'Rejection notifier inicializado',
            transactional_id=self._transactional_id,
            topic=self.settings.kafka_rejection_notifications_topic
        )

    async def notify_rejection(
        self,
        plan_id: str,
        intent_id: str,
        rejection_reason: Optional[str],
        correlation_id: Optional[str] = None,
        rejected_by: Optional[str] = None,
        risk_band: Optional[str] = None
    ) -> None:
        """
        Publica notificação de rejeição de plano.

        Args:
            plan_id: ID do plano rejeitado
            intent_id: ID do intent original
            rejection_reason: Motivo da rejeição
            correlation_id: ID de correlação para rastreamento
            rejected_by: Usuário ou sistema que rejeitou
            risk_band: Banda de risco do plano rejeitado
        """
        topic = self.settings.kafka_rejection_notifications_topic

        notification = {
            'plan_id': plan_id,
            'intent_id': intent_id,
            'rejection_reason': rejection_reason,
            'correlation_id': correlation_id,
            'rejected_by': rejected_by,
            'risk_band': risk_band,
            'event_type': 'plan_rejected'
        }

        try:
            self.producer.begin_transaction()

            value = json.dumps(notification, default=str).encode('utf-8')

            headers = [
                ('plan-id', plan_id.encode('utf-8')),
                ('intent-id', intent_id.encode('utf-8')),
                ('event-type', b'plan_rejected'),
                ('content-type', b'application/json'),
            ]

            if correlation_id:
                headers.append(('correlation-id', correlation_id.encode('utf-8')))

            if risk_band:
                headers.append(('risk-band', risk_band.encode('utf-8')))

            # Partition key pelo intent_id para manter ordem por intent
            key = intent_id.encode('utf-8')

            self.producer.produce(
                topic=topic,
                key=key,
                value=value,
                headers=headers,
                on_delivery=self._delivery_callback
            )

            self.producer.flush()
            self.producer.commit_transaction()

            logger.info(
                'Notificação de rejeição publicada',
                plan_id=plan_id,
                intent_id=intent_id,
                rejection_reason=rejection_reason,
                correlation_id=correlation_id,
                topic=topic
            )

        except Exception as e:
            logger.error(
                'Erro ao publicar notificação de rejeição',
                plan_id=plan_id,
                intent_id=intent_id,
                error=str(e)
            )
            self.producer.abort_transaction()
            raise

    def _delivery_callback(self, err, msg):
        """Callback de entrega de mensagens"""
        if err:
            logger.error(
                'Falha na entrega da notificação de rejeição',
                error=err,
                topic=msg.topic()
            )
        else:
            logger.debug(
                'Notificação de rejeição entregue',
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset()
            )

    async def close(self):
        """Fecha producer gracefully"""
        if self.producer:
            self.producer.flush()
            logger.info('Rejection notifier fechado')
