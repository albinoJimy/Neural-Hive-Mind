"""
Consumer Kafka para alertas SLA - Envia notificações para Slack/PagerDuty.

Este consumer consome alertas vindos do sla-management-system e despacha
notificações externas via Slack e PagerDuty.
"""

import json
import time
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer
from tenacity import retry, stop_after_attempt, wait_exponential

from src.clients.pagerduty_client import PagerDutyClient
from src.clients.slack_client import SlackClient
from src.config.settings import get_settings
from src.observability.metrics import get_metrics

logger = structlog.get_logger(__name__)


class SLAAlertConsumer:
    """Consumer Kafka para alertas SLA vindos do sla-management-system."""

    TOPICS = ["sla.alerts", "sla.violations"]

    def __init__(
        self,
        slack_client: SlackClient | None = None,
        pagerduty_client: PagerDutyClient | None = None,
    ):
        """
        Inicializa o consumer.

        Args:
            slack_client: Cliente Slack (opcional - cria se não fornecido)
            pagerduty_client: Cliente PagerDuty (opcional - cria se não fornecido)
        """
        config = get_settings()
        self.config = config
        self.logger = logger
        self.consumer: AIOKafkaConsumer | None = None
        self.running = False

        # Criar clientes se não fornecidos
        self.slack_client = slack_client or SlackClient()
        self.pagerduty_client = pagerduty_client or PagerDutyClient()

    async def start(self):
        """Inicia o consumer Kafka."""
        config = get_settings()

        consumer_config = {
            "bootstrap_servers": config.kafka_bootstrap_servers,
            "group_id": "orchestrator-sla-alerts",
            "auto_offset_reset": "latest",
            "enable_auto_commit": True,
        }

        # Configurar segurança se necessário
        security_protocol = getattr(config, "kafka_security_protocol", "PLAINTEXT")
        if security_protocol != "PLAINTEXT":
            consumer_config["security_protocol"] = security_protocol
            consumer_config["sasl_mechanism"] = getattr(config, "kafka_sasl_mechanism", "PLAIN")
            consumer_config["sasl_plain_username"] = config.kafka_sasl_username
            consumer_config["sasl_plain_password"] = config.kafka_sasl_password

        self.consumer = AIOKafkaConsumer(*self.TOPICS, **consumer_config)
        await self.consumer.start()

        self.logger.info(
            "sla_alert_consumer_started",
            topics=self.TOPICS,
            group_id="orchestrator-sla-alerts",
        )

    async def stop(self):
        """Para o consumer Kafka."""
        if self.consumer:
            await self.consumer.stop()
            self.logger.info("sla_alert_consumer_stopped")

    async def consume(self):
        """Consome e processa mensagens de alerta."""
        if not self.consumer:
            raise RuntimeError("Consumer not started")

        self.logger.info("sla_alert_consumer_consuming_loop_started")

        async def process_message(msg):
            """Processa uma mensagem individual."""
            try:
                alert_data = json.loads(msg.value)

                severity = alert_data.get("severity", "INFO")
                alert_type = alert_data.get("alert_type", "UNKNOWN")

                self.logger.info(
                    "processing_sla_alert",
                    alert_id=alert_data.get("alert_id"),
                    alert_type=alert_type,
                    severity=severity,
                )

                # Despachar baseado na severidade
                if severity in ["CRITICAL", "EMERGENCY"]:
                    await self._dispatch_critical(alert_data)
                else:
                    await self._dispatch_warning(alert_data)

            except Exception as e:
                self.logger.error(
                    "failed_to_process_sla_alert",
                    error=str(e),
                    topic=msg.topic,
                    partition=msg.partition,
                    offset=msg.offset,
                )

        async for msg in self.consumer:
            await process_message(msg)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
    )
    async def _dispatch_critical(self, alert_data: dict[str, Any]):
        """
        Despacha alerta crítico para PagerDuty + Slack.

        Args:
            alert_data: Dados do alerta
        """
        alert_id = alert_data.get("alert_id", "unknown")
        severity = alert_data.get("severity", "CRITICAL")

        try:
            metrics = get_metrics()
        except Exception:
            metrics = None

        # PagerDuty
        if self.pagerduty_client.is_configured():
            start_time = time.time()
            try:
                await self.pagerduty_client.trigger_alert(
                    dedup_key=alert_id,
                    event_type="trigger",
                    payload={
                        "summary": alert_data.get("title", ""),
                        "severity": alert_data.get("severity", ""),
                        "source": "orchestrator-dynamic",
                        "timestamp": alert_data.get("timestamp", ""),
                        "details": alert_data.get("details", alert_data),
                    },
                )
                duration = time.time() - start_time
                if metrics:
                    metrics.record_sla_notification_sent("pagerduty", severity)
                    metrics.record_sla_notification_duration("pagerduty", duration)
                self.logger.info("pagerduty_alert_sent", alert_id=alert_id)
            except Exception as e:
                if metrics:
                    metrics.record_sla_notification_failed("pagerduty", type(e).__name__)
                self.logger.error("pagerduty_send_failed", alert_id=alert_id, error=str(e))

        # Slack
        if self.slack_client.is_configured():
            start_time = time.time()
            try:
                await self.slack_client.send_message(
                    text=self._format_critical_message(alert_data),
                    channel="#sla-alerts-critical" if severity == "CRITICAL" else "#sla-alerts",
                    blocks=self._format_critical_blocks(alert_data),
                )
                duration = time.time() - start_time
                if metrics:
                    metrics.record_sla_notification_sent("slack", severity)
                    metrics.record_sla_notification_duration("slack", duration)
                self.logger.info("slack_alert_sent", alert_id=alert_id)
            except Exception as e:
                if metrics:
                    metrics.record_sla_notification_failed("slack", type(e).__name__)
                self.logger.error("slack_send_failed", alert_id=alert_id, error=str(e))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
    )
    async def _dispatch_warning(self, alert_data: dict[str, Any]):
        """
        Despacha alerta de warning para Slack.

        Args:
            alert_data: Dados do alerta
        """
        alert_id = alert_data.get("alert_id", "unknown")
        severity = alert_data.get("severity", "WARNING")

        try:
            metrics = get_metrics()
        except Exception:
            metrics = None

        if self.slack_client.is_configured():
            start_time = time.time()
            try:
                await self.slack_client.send_message(
                    text=self._format_warning_message(alert_data),
                    channel="#sla-alerts",
                    blocks=self._format_warning_blocks(alert_data),
                )
                duration = time.time() - start_time
                if metrics:
                    metrics.record_sla_notification_sent("slack", severity)
                    metrics.record_sla_notification_duration("slack", duration)
                self.logger.info("slack_alert_sent", alert_id=alert_id)
            except Exception as e:
                if metrics:
                    metrics.record_sla_notification_failed("slack", type(e).__name__)
                self.logger.error("slack_send_failed", alert_id=alert_id, error=str(e))

    def _format_critical_message(self, alert_data: dict[str, Any]) -> str:
        """Formata mensagem de alerta crítico."""
        title = alert_data.get("title", "SLA Critical Alert")
        alert_type = alert_data.get("alert_type", "UNKNOWN")
        service = alert_data.get("service_name", "orchestrator-dynamic")

        return f":rotating_light: *{title}* | {alert_type} | Service: {service}"

    def _format_warning_message(self, alert_data: dict[str, Any]) -> str:
        """Formata mensagem de alerta de warning."""
        title = alert_data.get("title", "SLA Warning")
        alert_type = alert_data.get("alert_type", "UNKNOWN")

        return f":warning: *{title}* | {alert_type}"

    def _format_critical_blocks(self, alert_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Formata blocos Slack para alerta crítico."""
        return [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":rotating_light: CRITICAL SLA ALERT",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Title:* {alert_data.get('title', 'Unknown')}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Severity:* {alert_data.get('severity', 'UNKNOWN')}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Workflow:* `{alert_data.get('workflow_id', 'N/A')}`",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Service:* {alert_data.get('service_name', 'orchestrator-dynamic')}",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View in Grafana",
                        },
                        "url": "https://grafana.example.com/d/sla-dashboard",
                    },
                ],
            },
        ]

    def _format_warning_blocks(self, alert_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Formata blocos Slack para alerta de warning."""
        return [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":warning: SLA Warning",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Title:* {alert_data.get('title', 'Unknown')}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Alert Type:* {alert_data.get('alert_type', 'UNKNOWN')}",
                },
            },
        ]
