"""
Serviço de despacho de alertas para múltiplos canais.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import structlog

from ..models.alert_rule import (
    Alert,
    AlertChannel,
    AlertDispatchResult,
)

logger = structlog.get_logger(__name__)


class AlertDispatcher:
    """Despacha alertas para múltiplos canais de notificação."""

    def __init__(
        self,
        slack_webhook_url: Optional[str] = None,
        pagerduty_routing_key: Optional[str] = None,
        smtp_host: Optional[str] = None,
        smtp_port: int = 587,
        smtp_username: Optional[str] = None,
        smtp_password: Optional[str] = None,
        smtp_from: Optional[str] = None,
    ):
        self.slack_webhook_url = slack_webhook_url
        self.pagerduty_routing_key = pagerduty_routing_key
        self.smtp_config = {
            "host": smtp_host,
            "port": smtp_port,
            "username": smtp_username,
            "password": smtp_password,
            "from": smtp_from,
        }
        self.session: Optional[httpx.AsyncClient] = None
        self.logger = logger

    async def connect(self):
        """Inicializa cliente HTTP."""
        self.session = httpx.AsyncClient(timeout=30.0)
        self.logger.info("alert_dispatcher_connected")

    async def disconnect(self):
        """Fecha cliente HTTP."""
        if self.session:
            await self.session.aclose()
            self.logger.info("alert_dispatcher_disconnected")

    async def dispatch(
        self, alert: Alert, channels: List[AlertChannel], channel_config: Dict[str, Dict[str, Any]]
    ) -> List[AlertDispatchResult]:
        """
        Despacha alerta para múltiplos canais em paralelo.

        Args:
            alert: Alerta a ser despachado
            channels: Lista de canais
            channel_config: Configurações específicas por canal

        Returns:
            Lista de resultados por canal
        """
        tasks = []

        for channel in channels:
            # Usa config específica do canal ou default
            config = channel_config.get(channel.value, {})

            if channel == AlertChannel.SLACK:
                tasks.append(self._dispatch_to_slack(alert, config))
            elif channel == AlertChannel.PAGERDUTY:
                tasks.append(self._dispatch_to_pagerduty(alert, config))
            elif channel == AlertChannel.EMAIL:
                tasks.append(self._dispatch_to_email(alert, config))
            elif channel == AlertChannel.WEBHOOK:
                tasks.append(self._dispatch_to_webhook(alert, config))
            elif channel == AlertChannel.ALERTMANAGER:
                tasks.append(self._dispatch_to_alertmanager(alert, config))

        # Executa todos os dispatches em paralelo
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Processa resultados
        dispatch_results = []
        for i, result in enumerate(results):
            if isinstance(result, AlertDispatchResult):
                dispatch_results.append(result)
            elif isinstance(result, Exception):
                channel = channels[i]
                dispatch_results.append(
                    AlertDispatchResult(
                        alert_id=alert.alert_id,
                        channel=channel,
                        success=False,
                        error_message=str(result),
                        dispatched_at=datetime.now(timezone.utc),
                    )
                )

        return dispatch_results

    async def _dispatch_to_slack(self, alert: Alert, config: Dict[str, Any]) -> AlertDispatchResult:
        """Despacha alerta para Slack."""
        try:
            webhook_url = config.get("webhook_url") or self.slack_webhook_url
            if not webhook_url:
                return AlertDispatchResult(
                    alert_id=alert.alert_id,
                    channel=AlertChannel.SLACK,
                    success=False,
                    error_message="No webhook URL configured",
                    dispatched_at=datetime.now(timezone.utc),
                )

            # Formatar mensagem Slack
            severity = alert.severity if isinstance(alert.severity, str) else alert.severity.value
            color = self._get_color_for_severity(severity)
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{'🚨' if severity in ['critical', 'emergency'] else '⚠️'} {alert.title}",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Severity:*\n{severity}"},
                        {"type": "mrkdwn", "text": f"*Service:*\n{alert.service_name or 'N/A'}"},
                        {"type": "mrkdwn", "text": f"*SLO ID:*\n{alert.slo_id or 'N/A'}"},
                        {
                            "type": "mrkdwn",
                            "text": f"*Triggered:*\n{alert.triggered_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                        },
                    ],
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Message:*\n{alert.message}"},
                },
            ]

            # Adicionar detalhes se existirem
            if alert.details:
                details_text = "\n".join([f"• *{k}*: {v}" for k, v in alert.details.items()])
                blocks.append(
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*Details:*\n{details_text}"},
                    }
                )

            payload = {"blocks": blocks, "attachments": [{"color": color}] if color else []}

            response = await self.session.post(webhook_url, json=payload)
            response.raise_for_status()

            self.logger.info(
                "alert_dispatched_to_slack",
                alert_id=alert.alert_id,
                status_code=response.status_code,
            )

            return AlertDispatchResult(
                alert_id=alert.alert_id,
                channel=AlertChannel.SLACK,
                success=True,
                dispatched_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            self.logger.error("slack_dispatch_failed", alert_id=alert.alert_id, error=str(e))
            return AlertDispatchResult(
                alert_id=alert.alert_id,
                channel=AlertChannel.SLACK,
                success=False,
                error_message=str(e),
                dispatched_at=datetime.now(timezone.utc),
            )

    async def _dispatch_to_pagerduty(
        self, alert: Alert, config: Dict[str, Any]
    ) -> AlertDispatchResult:
        """Despacha alerta para PagerDuty (v2 Events API)."""
        try:
            routing_key = config.get("routing_key") or self.pagerduty_routing_key
            if not routing_key:
                return AlertDispatchResult(
                    alert_id=alert.alert_id,
                    channel=AlertChannel.PAGERDUTY,
                    success=False,
                    error_message="No routing key configured",
                    dispatched_at=datetime.now(timezone.utc),
                )

            # PagerDuty Events API v2
            url = "https://events.pagerduty.com/v2/enqueue"

            severity = alert.severity if isinstance(alert.severity, str) else alert.severity.value
            payload = {
                "routing_key": routing_key,
                "event_action": "trigger",
                "payload": {
                    "summary": alert.title,
                    "severity": self._map_severity_to_pd(severity),
                    "source": alert.service_name or "sla-management-system",
                    "timestamp": alert.triggered_at.isoformat(),
                    "custom_details": alert.details,
                },
                "dedup_key": alert.alert_id,  # Usar alert_id como dedup key
            }

            response = await self.session.post(url, json=payload)
            response.raise_for_status()

            self.logger.info(
                "alert_dispatched_to_pagerduty",
                alert_id=alert.alert_id,
                status_code=response.status_code,
            )

            return AlertDispatchResult(
                alert_id=alert.alert_id,
                channel=AlertChannel.PAGERDUTY,
                success=True,
                dispatched_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            self.logger.error("pagerduty_dispatch_failed", alert_id=alert.alert_id, error=str(e))
            return AlertDispatchResult(
                alert_id=alert.alert_id,
                channel=AlertChannel.PAGERDUTY,
                success=False,
                error_message=str(e),
                dispatched_at=datetime.now(timezone.utc),
            )

    async def _dispatch_to_email(self, alert: Alert, config: Dict[str, Any]) -> AlertDispatchResult:
        """Despacha alerta via email."""
        try:
            # Nota: Implementação real requer biblioteca SMTP (smtplib, aiosmtplib)
            # Aqui simulamos o envio para simplificar
            to_addresses = config.get("to", [])
            if not to_addresses:
                return AlertDispatchResult(
                    alert_id=alert.alert_id,
                    channel=AlertChannel.EMAIL,
                    success=False,
                    error_message="No recipients configured",
                    dispatched_at=datetime.now(timezone.utc),
                )

            # Simular envio de email (em produção, usar aiosmtplib)
            self.logger.info(
                "email_dispatch_simulated",
                alert_id=alert.alert_id,
                to=to_addresses,
                subject=alert.title,
            )

            # TODO: Implementar envio real com aiosmtplib
            # from aiosmtplib import SMTP
            # async with SMTP(
            #     hostname=self.smtp_config["host"],
            #     port=self.smtp_config["port"],
            #     use_tls=True
            # ) as smtp:
            #     await smtp.login(
            #         self.smtp_config["username"],
            #         self.smtp_config["password"]
            #     )
            #     await smtp.send_message(message)

            return AlertDispatchResult(
                alert_id=alert.alert_id,
                channel=AlertChannel.EMAIL,
                success=True,
                dispatched_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            self.logger.error("email_dispatch_failed", alert_id=alert.alert_id, error=str(e))
            return AlertDispatchResult(
                alert_id=alert.alert_id,
                channel=AlertChannel.EMAIL,
                success=False,
                error_message=str(e),
                dispatched_at=datetime.now(timezone.utc),
            )

    async def _dispatch_to_webhook(
        self, alert: Alert, config: Dict[str, Any]
    ) -> AlertDispatchResult:
        """Despacha alerta para webhook genérico."""
        try:
            url = config.get("url")
            if not url:
                return AlertDispatchResult(
                    alert_id=alert.alert_id,
                    channel=AlertChannel.WEBHOOK,
                    success=False,
                    error_message="No webhook URL configured",
                    dispatched_at=datetime.now(timezone.utc),
                )

            headers = config.get("headers", {})
            method = config.get("method", "POST").upper()

            # Preparar payload
            severity = alert.severity if isinstance(alert.severity, str) else alert.severity.value
            payload = {
                "alert_id": alert.alert_id,
                "rule_id": alert.rule_id,
                "rule_name": alert.rule_name,
                "severity": severity,
                "title": alert.title,
                "message": alert.message,
                "details": alert.details,
                "slo_id": alert.slo_id,
                "service_name": alert.service_name,
                "triggered_at": alert.triggered_at.isoformat(),
            }

            if method == "POST":
                response = await self.session.post(url, json=payload, headers=headers)
            elif method == "PUT":
                response = await self.session.put(url, json=payload, headers=headers)
            else:
                response = await self.session.request(method, url, json=payload, headers=headers)

            response.raise_for_status()

            self.logger.info(
                "alert_dispatched_to_webhook",
                alert_id=alert.alert_id,
                url=url,
                status_code=response.status_code,
            )

            return AlertDispatchResult(
                alert_id=alert.alert_id,
                channel=AlertChannel.WEBHOOK,
                success=True,
                dispatched_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            self.logger.error("webhook_dispatch_failed", alert_id=alert.alert_id, error=str(e))
            return AlertDispatchResult(
                alert_id=alert.alert_id,
                channel=AlertChannel.WEBHOOK,
                success=False,
                error_message=str(e),
                dispatched_at=datetime.now(timezone.utc),
            )

    async def _dispatch_to_alertmanager(
        self, alert: Alert, config: Dict[str, Any]
    ) -> AlertDispatchResult:
        """Despacha alerta para Alertmanager."""
        try:
            alertmanager_url = config.get("url")
            if not alertmanager_url:
                return AlertDispatchResult(
                    alert_id=alert.alert_id,
                    channel=AlertChannel.ALERTMANAGER,
                    success=False,
                    error_message="No Alertmanager URL configured",
                    dispatched_at=datetime.now(timezone.utc),
                )

            # Formatar alerta para Alertmanager API
            severity = alert.severity if isinstance(alert.severity, str) else alert.severity.value
            alertmanager_payload = [
                {
                    "labels": {
                        "alertname": alert.rule_name,
                        "severity": severity,
                        "alert_id": alert.alert_id,
                    },
                    "annotations": {
                        "summary": alert.title,
                        "description": alert.message,
                        "slo_id": alert.slo_id or "",
                        "service": alert.service_name or "",
                    },
                    "generatorURL": f"sla-management-system://{alert.rule_id}",
                }
            ]

            # Adicionar detalhes como labels separados
            for key, value in alert.details.items():
                alertmanager_payload[0]["labels"][f"detail_{key}"] = str(value)

            response = await self.session.post(
                f"{alertmanager_url}/api/v1/alerts", json=alertmanager_payload
            )
            response.raise_for_status()

            self.logger.info(
                "alert_dispatched_to_alertmanager",
                alert_id=alert.alert_id,
                status_code=response.status_code,
            )

            return AlertDispatchResult(
                alert_id=alert.alert_id,
                channel=AlertChannel.ALERTMANAGER,
                success=True,
                dispatched_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            self.logger.error("alertmanager_dispatch_failed", alert_id=alert.alert_id, error=str(e))
            return AlertDispatchResult(
                alert_id=alert.alert_id,
                channel=AlertChannel.ALERTMANAGER,
                success=False,
                error_message=str(e),
                dispatched_at=datetime.now(timezone.utc),
            )

    def _get_color_for_severity(self, severity: str) -> str:
        """Retorna cor para Slack baseado na severidade."""
        colors = {
            "emergency": "#FF0000",  # Vermelho
            "critical": "#FF6600",  # Laranja
            "warning": "#FFCC00",  # Amarelo
            "info": "#36A64F",  # Verde
        }
        return colors.get(severity, "#36A64F")

    def _map_severity_to_pd(self, severity: str) -> str:
        """Mapeia severidade para PagerDuty severity."""
        mapping = {
            "emergency": "critical",
            "critical": "critical",
            "warning": "warning",
            "info": "info",
        }
        return mapping.get(severity, "info")
