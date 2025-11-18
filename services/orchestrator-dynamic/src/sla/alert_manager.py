"""
Alert Manager - Gerenciamento de Alertas Proativos de SLA

Responsável por publicar alertas proativos e eventos de violação no Kafka.
"""

import uuid
from datetime import datetime
from typing import Dict, Optional
import structlog

logger = structlog.get_logger(__name__)


class AlertManager:
    """
    Gerenciador de alertas proativos e eventos de violação SLA.

    Responsabilidades:
    - Publicar alertas proativos quando budget <20% ou deadline próximo
    - Publicar eventos de violação SLA no Kafka
    - Registrar métricas Prometheus de alertas enviados
    - Deduplicar alertas para evitar spam
    """

    def __init__(self, config, kafka_producer, metrics):
        """
        Inicializar Alert Manager.

        Args:
            config: Configurações do orchestrator (OrchestratorSettings)
            kafka_producer: Cliente Kafka para publicação
            metrics: Instância de OrchestratorMetrics
        """
        self.config = config
        self.kafka_producer = kafka_producer
        self.metrics = metrics
        self.redis = None  # Será injetado externamente

    def set_redis(self, redis_client):
        """Injetar cliente Redis para deduplicação."""
        self.redis = redis_client

    async def _should_send_alert(self, workflow_id: str, alert_type: str) -> bool:
        """
        Verificar cache de deduplicação para evitar alertas duplicados.

        Args:
            workflow_id: ID do workflow
            alert_type: Tipo do alerta

        Returns:
            bool: True se deve enviar alerta, False se já foi enviado recentemente
        """
        if not self.redis:
            # Sem Redis, sempre enviar (fail-open)
            return True

        cache_key = f"alert:sent:{workflow_id}:{alert_type}"

        try:
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(
                    "alert_deduplicated",
                    workflow_id=workflow_id,
                    alert_type=alert_type
                )
                self.metrics.record_sla_alert_deduplicated()
                return False
            return True

        except Exception as e:
            logger.warning(
                "deduplication_check_error",
                workflow_id=workflow_id,
                alert_type=alert_type,
                error=str(e)
            )
            # Em caso de erro, enviar alerta (fail-open)
            return True

    async def _cache_alert_sent(self, workflow_id: str, alert_type: str):
        """
        Registrar alerta enviado no cache com TTL.

        Args:
            workflow_id: ID do workflow
            alert_type: Tipo do alerta
        """
        if not self.redis:
            return

        cache_key = f"alert:sent:{workflow_id}:{alert_type}"

        try:
            await self.redis.setex(
                cache_key,
                self.config.sla_alert_deduplication_ttl_seconds,
                "1"
            )
        except Exception as e:
            logger.warning(
                "deduplication_cache_error",
                workflow_id=workflow_id,
                alert_type=alert_type,
                error=str(e)
            )

    async def send_proactive_alert(self, alert_type: str, context: Dict) -> bool:
        """
        Enviar alerta proativo.

        Args:
            alert_type: Tipo do alerta (BUDGET_CRITICAL, DEADLINE_APPROACHING, BURN_RATE_HIGH)
            context: Contexto do alerta com campos relevantes

        Returns:
            bool: True se alerta foi enviado, False se deduplicated ou se producer não configurado
        """
        workflow_id = context.get('workflow_id', 'unknown')

        # Validar se Kafka producer está configurado
        if self.kafka_producer is None:
            logger.error(
                "kafka_producer_not_configured",
                alert_type=alert_type,
                workflow_id=workflow_id
            )
            self.metrics.record_sla_monitor_error('producer_not_initialized')
            return False

        # Verificar deduplicação
        if not await self._should_send_alert(workflow_id, alert_type):
            return False

        try:
            # Determinar severidade
            severity = 'CRITICAL' if alert_type in ['BUDGET_CRITICAL', 'DEADLINE_APPROACHING'] else 'WARNING'

            # Construir payload do alerta
            alert_payload = {
                'alert_id': str(uuid.uuid4()),
                'event_type': 'ALERT',  # Distinguir de violações
                'alert_type': alert_type,
                'severity': severity,
                'service_name': context.get('service_name', 'orchestrator-dynamic'),
                'workflow_id': workflow_id,
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'context': context
            }

            # Publicar no Kafka (tópico dedicado para alertas proativos)
            topic = self.config.sla_alerts_topic
            await self.kafka_producer.publish_ticket(
                topic=topic,
                ticket=alert_payload
            )

            # Cachear alerta enviado
            await self._cache_alert_sent(workflow_id, alert_type)

            # Registrar métrica
            self.metrics.record_sla_alert_sent(alert_type, severity)

            logger.info(
                "proactive_alert_sent",
                alert_id=alert_payload['alert_id'],
                alert_type=alert_type,
                severity=severity,
                workflow_id=workflow_id
            )

            return True

        except Exception as e:
            logger.error(
                "proactive_alert_failed",
                alert_type=alert_type,
                workflow_id=workflow_id,
                error=str(e)
            )
            self.metrics.record_sla_monitor_error('alert_publish')
            return False

    async def send_budget_alert(
        self,
        workflow_id: str,
        service_name: str,
        budget_data: Dict
    ):
        """
        Enviar alerta específico para budget crítico.

        Args:
            workflow_id: ID do workflow
            service_name: Nome do serviço
            budget_data: Dados do budget (error_budget_remaining, status, burn_rates)
        """
        context = {
            'workflow_id': workflow_id,
            'service_name': service_name,
            'budget_remaining': budget_data.get('error_budget_remaining', 0),
            'status': budget_data.get('status', 'UNKNOWN'),
            'burn_rates': budget_data.get('burn_rates', [])
        }

        await self.send_proactive_alert('BUDGET_CRITICAL', context)

    async def send_deadline_alert(
        self,
        workflow_id: str,
        ticket_id: str,
        deadline_data: Dict
    ):
        """
        Enviar alerta específico para deadline próximo.

        Args:
            workflow_id: ID do workflow
            ticket_id: ID do ticket
            deadline_data: Dados do deadline (remaining_seconds, percent_consumed, sla_deadline)
        """
        context = {
            'workflow_id': workflow_id,
            'ticket_id': ticket_id,
            'remaining_seconds': deadline_data.get('remaining_seconds', 0),
            'percent_consumed': deadline_data.get('percent_consumed', 0),
            'sla_deadline': deadline_data.get('sla_deadline')
        }

        await self.send_proactive_alert('DEADLINE_APPROACHING', context)

    async def publish_sla_violation(self, violation: Dict):
        """
        Publicar evento de violação SLA no Kafka.

        Args:
            violation: Dict com campos da violação (seguindo schema documentado)
        """
        # Validar se Kafka producer está configurado
        if self.kafka_producer is None:
            logger.error(
                "kafka_producer_not_configured",
                violation_type=violation.get('violation_type'),
                workflow_id=violation.get('workflow_id'),
                ticket_id=violation.get('ticket_id')
            )
            self.metrics.record_sla_monitor_error('producer_not_initialized')
            return

        try:
            # Garantir campos obrigatórios
            violation_event = {
                'violation_id': violation.get('violation_id', str(uuid.uuid4())),
                'event_type': 'VIOLATION',  # Distinguir de alertas proativos
                'workflow_id': violation.get('workflow_id'),
                'ticket_id': violation.get('ticket_id'),
                'violation_type': violation.get('violation_type'),
                'service_name': violation.get('service_name', 'orchestrator-dynamic'),
                'sla_deadline': violation.get('sla_deadline'),
                'actual_completion': violation.get('actual_completion'),
                'delay_ms': violation.get('delay_ms'),
                'budget_remaining': violation.get('budget_remaining'),
                'severity': violation.get('severity', 'WARNING'),
                'metadata': violation.get('metadata', {}),
                'timestamp': violation.get('timestamp', datetime.utcnow().isoformat() + 'Z')
            }

            # Publicar no Kafka (tópico dedicado para violações formais)
            topic = self.config.sla_violations_topic
            await self.kafka_producer.publish_ticket(
                topic=topic,
                ticket=violation_event
            )

            # Registrar métrica
            violation_type = violation_event['violation_type']
            self.metrics.record_sla_violation_published(violation_type)

            logger.warning(
                "sla_violation_published",
                violation_id=violation_event['violation_id'],
                violation_type=violation_type,
                workflow_id=violation_event['workflow_id'],
                ticket_id=violation_event['ticket_id'],
                delay_ms=violation_event['delay_ms']
            )

        except Exception as e:
            logger.error(
                "violation_publish_failed",
                violation=violation,
                error=str(e)
            )
            self.metrics.record_sla_monitor_error('violation_publish')
