"""
Producer Kafka para publicar eventos de SLA.
"""

from typing import Dict, Any
import json
from aiokafka import AIOKafkaProducer
import structlog

from ..config.settings import KafkaSettings
from ..models.error_budget import ErrorBudget
from ..models.freeze_policy import FreezeEvent


class KafkaPublishError(Exception):
    """Erro ao publicar evento no Kafka."""
    pass


class KafkaProducerClient:
    """Producer Kafka para eventos de SLA."""

    def __init__(self, settings: KafkaSettings):
        self.settings = settings
        self.producer: AIOKafkaProducer = None
        self.logger = structlog.get_logger(__name__)

    async def start(self) -> None:
        """Inicializa producer."""
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.settings.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                **self.settings.producer_config
            )
            await self.producer.start()
            self.logger.info(
                "kafka_producer_started",
                bootstrap_servers=self.settings.bootstrap_servers
            )
        except Exception as e:
            self.logger.error("kafka_producer_start_failed", error=str(e))
            raise

    async def stop(self) -> None:
        """Flush pending messages e fecha producer."""
        if self.producer:
            await self.producer.stop()
            self.logger.info("kafka_producer_stopped")

    async def publish_budget_update(self, budget: ErrorBudget) -> None:
        """Publica evento de atualização de budget."""
        try:
            topic = self.settings.budget_topic
            key = budget.slo_id.encode('utf-8')
            value = budget.to_dict()

            headers = [
                ("event_type", b"budget.updated"),
                ("service_name", budget.service_name.encode('utf-8')),
                ("status", budget.status.value.encode('utf-8'))
            ]

            await self.producer.send(
                topic,
                value=value,
                key=key,
                headers=headers
            )

            self.logger.info(
                "budget_event_published",
                slo_id=budget.slo_id,
                topic=topic,
                status=budget.status.value
            )
        except Exception as e:
            self.logger.error(
                "budget_event_publish_failed",
                slo_id=budget.slo_id,
                error=str(e)
            )
            raise KafkaPublishError(f"Failed to publish budget event: {e}")

    async def publish_freeze_event(self, event: FreezeEvent, action: str) -> None:
        """Publica evento de freeze/unfreeze."""
        try:
            topic = self.settings.freeze_topic
            key = event.service_name.encode('utf-8')
            value = {
                "event_id": event.event_id,
                "policy_id": event.policy_id,
                "slo_id": event.slo_id,
                "service_name": event.service_name,
                "action": event.action.value,
                "triggered_at": event.triggered_at.isoformat(),
                "resolved_at": event.resolved_at.isoformat() if event.resolved_at else None,
                "trigger_reason": event.trigger_reason,
                "budget_remaining_percent": event.budget_remaining_percent,
                "burn_rate": event.burn_rate,
                "active": event.active
            }

            headers = [
                ("event_type", f"freeze.{action}".encode('utf-8')),
                ("policy_id", event.policy_id.encode('utf-8'))
            ]

            await self.producer.send(
                topic,
                value=value,
                key=key,
                headers=headers
            )

            self.logger.info(
                "freeze_event_published",
                event_id=event.event_id,
                service=event.service_name,
                action=action,
                topic=topic
            )
        except Exception as e:
            self.logger.error(
                "freeze_event_publish_failed",
                event_id=event.event_id,
                error=str(e)
            )
            raise KafkaPublishError(f"Failed to publish freeze event: {e}")

    async def publish_slo_violation(
        self,
        slo_id: str,
        service_name: str,
        details: Dict[str, Any]
    ) -> None:
        """Publica evento de violação de SLO."""
        try:
            topic = self.settings.violations_topic
            key = slo_id.encode('utf-8')
            value = {
                "slo_id": slo_id,
                "service_name": service_name,
                "timestamp": details.get("timestamp"),
                "severity": details.get("severity", "warning"),
                "details": details
            }

            headers = [
                ("event_type", b"slo.violation"),
                ("service_name", service_name.encode('utf-8'))
            ]

            await self.producer.send(
                topic,
                value=value,
                key=key,
                headers=headers
            )

            self.logger.info(
                "violation_event_published",
                slo_id=slo_id,
                service=service_name,
                topic=topic
            )
        except Exception as e:
            self.logger.error(
                "violation_event_publish_failed",
                slo_id=slo_id,
                error=str(e)
            )
            raise KafkaPublishError(f"Failed to publish violation event: {e}")

    async def health_check(self) -> bool:
        """Verifica se producer está conectado."""
        try:
            return self.producer is not None and not self.producer._closed
        except Exception:
            return False
