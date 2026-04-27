"""
Consumer Kafka para alertas SLA e despacho para canais de notificação.
"""

import json
from datetime import timezone
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer

logger = structlog.get_logger(__name__)


class SLAAlertConsumer:
    """
    Consumer Kafka para alertas SLA.

    Consome mensagens dos tópicos `sla.alerts` e `sla.violations`,
    processa-as e despacha para os canais apropriados:
    - Critical/Emergency: PagerDuty + Slack
    - Warning/Info: Slack apenas

    Mensagens devem ter o formato:
    {
        "alert_id": str,
        "severity": str,  # critical, emergency, warning, info
        "title": str,
        "message": str,
        "service_name": Optional[str],
        "slo_id": Optional[str],
        "error_budget_remaining": Optional[float],
        "details": Optional[Dict[str, Any]]
    }
    """

    CRITICAL_SEVERITIES = {"critical", "emergency"}

    def __init__(
        self,
        bootstrap_servers: list[str],
        topics: list[str],
        slack_client,
        pagerduty_client,
        group_id: str = "sla-alert-consumer",
        auto_offset_reset: str = "latest",
    ):
        """
        Inicializa consumer SLA Alert.

        Args:
            bootstrap_servers: Lista de servidores Kafka
            topics: Tópicos para consumir
            slack_client: Cliente Slack para notificações
            pagerduty_client: Cliente PagerDuty para notificações
            group_id: ID do consumer group
            auto_offset_reset: Estratégia de offset (latest, earliest)
        """
        self.bootstrap_servers = bootstrap_servers
        self.topics = topics
        self.slack_client = slack_client
        self.pagerduty_client = pagerduty_client
        self.group_id = group_id
        self.auto_offset_reset = auto_offset_reset

        self.consumer: AIOKafkaConsumer | None = None
        self.is_running = False
        self.logger = logger

    async def start(self):
        """Inicia o consumer Kafka."""
        self.consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            auto_offset_reset=self.auto_offset_reset,
            enable_auto_commit=True,
            value_deserializer=lambda m: m.decode("utf-8") if m else None,
        )
        await self.consumer.start()
        self.is_running = True
        self.logger.info(
            "sla_alert_consumer_started",
            topics=self.topics,
            group_id=self.group_id,
        )

    async def stop(self):
        """Para o consumer Kafka."""
        if self.consumer:
            await self.consumer.stop()
            self.consumer = None
        self.is_running = False
        self.logger.info("sla_alert_consumer_stopped")

    async def consume(self):
        """
        Loop principal de consumo.

        Processa mensagens continuamente até que is_running seja False.
        """
        if not self.consumer:
            raise RuntimeError("Consumer not started. Call start() first.")

        self.logger.info("sla_alert_consume_loop_started")

        try:
            async for message in self.consumer:
                if not self.is_running:
                    break
                await self._process_message(message)

        except Exception as e:
            self.logger.error("consume_loop_error", error=str(e))
            raise

    async def _process_message(self, message):
        """
        Processa mensagem individual.

        Args:
            message: Mensagem Kafka (ConsumerRecord)
        """
        try:
            # Decodificar valor
            value = message.value
            if not value:
                self.logger.warning("empty_message_received", topic=message.topic)
                return

            # Parse JSON
            alert_data = json.loads(value)

            # Validar campos obrigatórios
            if not all(k in alert_data for k in ["alert_id", "severity", "title", "message"]):
                self.logger.warning(
                    "invalid_alert_message",
                    alert_id=alert_data.get("alert_id"),
                    missing_fields="alert_id, severity, title, or message",
                )
                return

            # Despachar baseado na severidade
            severity = alert_data.get("severity", "").lower()

            if self._is_critical_severity(severity):
                await self._dispatch_critical(alert_data)
            else:
                await self._dispatch_warning(alert_data)

            self.logger.debug(
                "alert_processed",
                alert_id=alert_data.get("alert_id"),
                severity=severity,
            )

        except json.JSONDecodeError as e:
            self.logger.error(
                "json_decode_error",
                topic=message.topic,
                partition=message.partition,
                offset=message.offset,
                error=str(e),
            )

        except Exception as e:
            self.logger.error(
                "process_message_error",
                topic=message.topic,
                error=str(e),
            )

    async def _dispatch_critical(self, alert_data: dict[str, Any]):
        """
        Despacha alerta crítico para PagerDuty e Slack.

        Args:
            alert_data: Dados do alerta
        """
        alert_id = alert_data.get("alert_id", "unknown")
        severity = alert_data.get("severity", "critical")

        # Enviar para PagerDuty
        try:
            await self.pagerduty_client.send_sla_alert(
                alert_id=alert_id,
                severity=severity,
                title=alert_data.get("title", "SLA Alert"),
                message=alert_data.get("message", ""),
                service_name=alert_data.get("service_name"),
                slo_id=alert_data.get("slo_id"),
                error_budget_remaining=alert_data.get("error_budget_remaining"),
                details=alert_data.get("details"),
            )
            self.logger.info("pagerduty_alert_sent", alert_id=alert_id)
        except Exception as e:
            self.logger.error("pagerduty_dispatch_failed", alert_id=alert_id, error=str(e))

        # Enviar para Slack
        try:
            await self.slack_client.send_sla_alert(
                alert_id=alert_id,
                severity=severity,
                title=alert_data.get("title", "SLA Alert"),
                message=alert_data.get("message", ""),
                service_name=alert_data.get("service_name"),
                slo_id=alert_data.get("slo_id"),
                error_budget_remaining=alert_data.get("error_budget_remaining"),
                details=alert_data.get("details"),
            )
            self.logger.info("slack_alert_sent", alert_id=alert_id)
        except Exception as e:
            self.logger.error("slack_dispatch_failed", alert_id=alert_id, error=str(e))

    async def _dispatch_warning(self, alert_data: dict[str, Any]):
        """
        Despacha alerta warning/info apenas para Slack.

        Args:
            alert_data: Dados do alerta
        """
        alert_id = alert_data.get("alert_id", "unknown")
        severity = alert_data.get("severity", "warning")

        try:
            await self.slack_client.send_sla_alert(
                alert_id=alert_id,
                severity=severity,
                title=alert_data.get("title", "SLA Alert"),
                message=alert_data.get("message", ""),
                service_name=alert_data.get("service_name"),
                slo_id=alert_data.get("slo_id"),
                error_budget_remaining=alert_data.get("error_budget_remaining"),
                details=alert_data.get("details"),
            )
            self.logger.info("slack_alert_sent", alert_id=alert_id)
        except Exception as e:
            self.logger.error("slack_dispatch_failed", alert_id=alert_id, error=str(e))

    def _is_critical_severity(self, severity: str) -> bool:
        """
        Verifica se severidade é crítica (requer PagerDuty).

        Args:
            severity: String de severidade

        Returns:
            True se for critical ou emergency
        """
        return severity.lower() in self.CRITICAL_SEVERITIES

    def _get_emoji(self, severity: str) -> str:
        """Retorna emoji para severidade."""
        emojis = {
            "emergency": ":rotating_light:",
            "critical": ":warning:",
            "warning": ":large_orange_diamond:",
            "info": ":information_source:",
        }
        return emojis.get(severity.lower(), ":white_circle:")

    def _format_slack_blocks(self, alert_data: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Formata blocks Slack para alerta.

        Args:
            alert_data: Dados do alerta

        Returns:
            Lista de blocks Slack
        """
        from datetime import datetime

        severity = alert_data.get("severity", "info").lower()
        emoji = self._get_emoji(severity)

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {alert_data.get('title', 'SLA Alert')}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Severity:*\n{severity.upper()}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Service:*\n{alert_data.get('service_name', 'N/A')}",
                    },
                    {"type": "mrkdwn", "text": f"*SLO ID:*\n{alert_data.get('slo_id', 'N/A')}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Triggered:*\n{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                    },
                ],
            },
        ]

        # Adicionar error budget se disponível
        if alert_data.get("error_budget_remaining") is not None:
            blocks.append(
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Error Budget:*\n{alert_data['error_budget_remaining']:.1f}%",
                        }
                    ],
                }
            )

        # Adicionar mensagem
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Message:*\n{alert_data.get('message', '')}"},
            }
        )

        # Adicionar detalhes se existirem
        if alert_data.get("details"):
            details_text = "\n".join([f"• *{k}*: {v}" for k, v in alert_data["details"].items()])
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Details:*\n{details_text}"},
                }
            )

        # Footer com alert_id
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Alert ID: `{alert_data.get('alert_id', 'unknown')}` | SLA Management System",
                    }
                ],
            }
        )

        return blocks

    async def health_check(self) -> bool:
        """Verifica se consumer está saudável."""
        return self.is_running and self.consumer is not None
