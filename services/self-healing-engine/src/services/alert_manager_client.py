"""Alert Manager Client para Self-Healing Engine.

Envia alertas para sistemas externos quando incidentes são detectados:
- AlertManager (Prometheus)
- Slack webhooks
- PagerDuty API
"""

import asyncio
from enum import Enum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

import httpx
import structlog

from neural_hive_observability import get_tracer

logger = structlog.get_logger()
_tracer = get_tracer()


def _start_span(name):
    """Inicia um span OTEL, ou noop context se tracer indisponível."""
    if _tracer is None:
        from contextlib import nullcontext
        return nullcontext()
    return _tracer.start_as_current_span(name)


class AlertSeverity(str, Enum):
    """Níveis de severidade para alertas."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Alerta para envio ao AlertManager."""

    alert_name: str
    severity: AlertSeverity
    summary: str
    description: str
    labels: Dict[str, str]
    annotations: Dict[str, str]
    fingerprint: Optional[str] = None
    generator_url: Optional[str] = None


class AlertManagerClient:
    """Cliente para enviar alertas ao AlertManager/PagerDuty/Slack."""

    def __init__(
        self,
        alertmanager_url: Optional[str] = None,
        slack_webhook_url: Optional[str] = None,
        pagerduty_routing_key: Optional[str] = None,
        timeout_seconds: int = 10,
        enabled: bool = True,
    ):
        """Inicializa o cliente de alertas.

        Args:
            alertmanager_url: URL do AlertManager (ex: http://alertmanager:9093/api/v1/alerts)
            slack_webhook_url: URL do webhook Slack
            pagerduty_routing_key: Routing key do PagerDuty Events API
            timeout_seconds: Timeout para requisições HTTP
            enabled: Se o cliente está habilitado
        """
        self.alertmanager_url = alertmanager_url
        self.slack_webhook_url = slack_webhook_url
        self.pagerduty_routing_key = pagerduty_routing_key
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled

        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def send_alert(self, alert: Alert) -> bool:
        """Envia um alerta para todos os canais configurados.

        Args:
            alert: Alerta para enviar

        Returns:
            True se enviado com sucesso para pelo menos um canal
        """
        if not self.enabled:
            logger.debug("alert_client.disabled", alert_name=alert.alert_name)
            return False

        with _start_span("alert.send") as span:
            success_count = 0

            # Enviar para AlertManager
            if self.alertmanager_url:
                if await self._send_to_alertmanager(alert):
                    success_count += 1

            # Enviar para Slack
            if self.slack_webhook_url:
                if await self._send_to_slack(alert):
                    success_count += 1

            # Enviar para PagerDuty
            if self.pagerduty_routing_key:
                if await self._send_to_pagerduty(alert):
                    success_count += 1

            logger.info(
                "alert_client.sent",
                alert_name=alert.alert_name,
                severity=alert.severity,
                success_count=success_count,
            )

            return success_count > 0

    async def _send_to_alertmanager(self, alert: Alert) -> bool:
        """Envia alerta para o AlertManager."""
        try:
            payload = [
                {
                    "labels": {
                        "alertname": alert.alert_name,
                        "severity": alert.severity.value,
                        "service": "self-healing-engine",
                        **alert.labels,
                    },
                    "annotations": {
                        "summary": alert.summary,
                        "description": alert.description,
                        **alert.annotations,
                    },
                    "generatorURL": alert.generator_url,
                }
            ]

            if alert.fingerprint:
                payload[0]["fingerprint"] = alert.fingerprint

            response = await self._client.post(
                f"{self.alertmanager_url}",
                json=payload,
            )

            if response.status_code in (200, 202):
                logger.debug("alert_client.alertmanager_success", alert_name=alert.alert_name)
                return True
            else:
                logger.warning(
                    "alert_client.alertmanager_failed",
                    alert_name=alert.alert_name,
                    status_code=response.status_code,
                )
                return False

        except Exception as e:
            logger.error("alert_client.alertmanager_error", alert_name=alert.alert_name, error=str(e))
            return False

    async def _send_to_slack(self, alert: Alert) -> bool:
        """Envia alerta para Slack via webhook."""
        try:
            # Cores para severidade
            color_map = {
                AlertSeverity.INFO: "#36a64f",  # blue
                AlertSeverity.WARNING: "#ff9800",  # orange
                AlertSeverity.ERROR: "#f44336",  # red
                AlertSeverity.CRITICAL: "#9c27b0",  # purple
            }

            payload = {
                "attachments": [
                    {
                        "color": color_map.get(alert.severity, "#36a64f"),
                        "title": f"[{alert.severity.value.upper()}] {alert.summary}",
                        "text": alert.description,
                        "fields": [
                            {"title": "Severity", "value": alert.severity.value, "short": True},
                            {"title": "Service", "value": "self-healing-engine", "short": True},
                        ],
                        "footer": "Neural Hive Mind - Self-Healing Engine",
                        "ts": int(asyncio.get_event_loop().time()),
                    }
                ]
            }

            # Adicionar labels como fields
            for key, value in alert.labels.items():
                payload["attachments"][0]["fields"].append({"title": key, "value": value, "short": True})

            response = await self._client.post(self.slack_webhook_url, json=payload)

            if response.status_code == 200:
                logger.debug("alert_client.slack_success", alert_name=alert.alert_name)
                return True
            else:
                logger.warning(
                    "alert_client.slack_failed",
                    alert_name=alert.alert_name,
                    status_code=response.status_code,
                )
                return False

        except Exception as e:
            logger.error("alert_client.slack_error", alert_name=alert.alert_name, error=str(e))
            return False

    async def _send_to_pagerduty(self, alert: Alert) -> bool:
        """Envia alerta para PagerDuty via Events API v2."""
        try:
            # Mapear severidade para PagerDuty severity
            pd_severity_map = {
                AlertSeverity.INFO: "info",
                AlertSeverity.WARNING: "warning",
                AlertSeverity.ERROR: "error",
                AlertSeverity.CRITICAL: "critical",
            }

            payload = {
                "routing_key": self.pagerduty_routing_key,
                "event_action": "trigger",
                "payload": {
                    "summary": alert.summary,
                    "severity": pd_severity_map.get(alert.severity, "error"),
                    "source": "self-healing-engine",
                    "custom_details": {
                        "description": alert.description,
                        "labels": alert.labels,
                        "annotations": alert.annotations,
                    },
                },
                "dedup_key": alert.fingerprint,
            }

            response = await self._client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
            )

            if response.status_code == 202:
                logger.debug("alert_client.pagerduty_success", alert_name=alert.alert_name)
                return True
            else:
                logger.warning(
                    "alert_client.pagerduty_failed",
                    alert_name=alert.alert_name,
                    status_code=response.status_code,
                )
                return False

        except Exception as e:
            logger.error("alert_client.pagerduty_error", alert_name=alert.alert_name, error=str(e))
            return False

    async def send_batch_alerts(self, alerts: List[Alert]) -> Dict[str, int]:
        """Envia múltiplos alertas em batch.

        Args:
            alerts: Lista de alertas para enviar

        Returns:
            Dict com contagem de sucessos e falhas
        """
        results = {"success": 0, "failed": 0}

        for alert in alerts:
            success = await self.send_alert(alert)
            if success:
                results["success"] += 1
            else:
                results["failed"] += 1

        return results

    async def close(self):
        """Fecha o cliente HTTP."""
        await self._client.aclose()

    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()


# Convenience functions para alertas comuns

async def alert_deadlock_detected(
    workflow_id: str,
    stuck_duration_seconds: int,
    suspected_tickets: List[str],
    alert_client: AlertManagerClient,
):
    """Envia alerta de deadlock detectado."""
    alert = Alert(
        alert_name="DeadlockDetected",
        severity=AlertSeverity.ERROR,
        summary=f"Deadlock detected in workflow {workflow_id}",
        description=f"Workflow {workflow_id} stuck for {stuck_duration_seconds}s. "
        f"Suspected tickets: {', '.join(suspected_tickets)}",
        labels={
            "workflow_id": workflow_id,
            "incident_type": "deadlock",
            "suspected_tickets": str(len(suspected_tickets)),
        },
        annotations={
            "stuck_duration_seconds": str(stuck_duration_seconds),
            "suspected_tickets": ",".join(suspected_tickets),
        },
        fingerprint=f"deadlock-{workflow_id}",
    )
    await alert_client.send_alert(alert)


async def alert_memory_leak_detected(
    pod_name: str,
    namespace: str,
    usage_percent: float,
    duration_above_threshold: int,
    alert_client: AlertManagerClient,
):
    """Envia alerta de memory leak detectado."""
    alert = Alert(
        alert_name="MemoryLeakDetected",
        severity=AlertSeverity.WARNING,
        summary=f"Memory leak detected in pod {pod_name}",
        description=f"Pod {namespace}/{pod_name} using {usage_percent:.1f}% memory "
        f"for {duration_above_threshold}s.",
        labels={
            "pod_name": pod_name,
            "namespace": namespace,
            "incident_type": "memory_leak",
        },
        annotations={
            "usage_percent": f"{usage_percent:.2f}",
            "duration_above_threshold": str(duration_above_threshold),
        },
        fingerprint=f"memory-leak-{namespace}-{pod_name}",
    )
    await alert_client.send_alert(alert)


async def alert_remediation_started(
    remediation_id: str,
    incident_type: str,
    playbook_name: str,
    alert_client: AlertManagerClient,
):
    """Envia alerta de remediação iniciada."""
    alert = Alert(
        alert_name="RemediationStarted",
        severity=AlertSeverity.INFO,
        summary=f"Remediation started for {incident_type}",
        description=f"Executing playbook {playbook_name} (ID: {remediation_id})",
        labels={
            "remediation_id": remediation_id,
            "incident_type": incident_type,
            "playbook_name": playbook_name,
        },
        annotations={
            "playbook": playbook_name,
        },
        fingerprint=f"remediation-{remediation_id}",
    )
    await alert_client.send_alert(alert)


async def alert_remediation_failed(
    remediation_id: str,
    error: str,
    alert_client: AlertManagerClient,
):
    """Envia alerta de falha na remediação."""
    alert = Alert(
        alert_name="RemediationFailed",
        severity=AlertSeverity.CRITICAL,
        summary=f"Remediation failed: {remediation_id}",
        description=f"Error: {error}",
        labels={
            "remediation_id": remediation_id,
            "status": "failed",
        },
        annotations={
            "error": error,
        },
        fingerprint=f"remediation-failed-{remediation_id}",
    )
    await alert_client.send_alert(alert)
