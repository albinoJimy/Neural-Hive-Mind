"""
DriftAlerter: Envia alertas quando drift é detectado.

Integra com Prometheus Alertmanager e pode enviar notificações
para Slack, email ou outros canais.
"""

import aiohttp
import json
from typing import Dict, List, Any
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


class DriftAlerter:
    """Envia alertas de drift."""

    def __init__(self, config: Dict[str, Any]):
        """
        Inicializa alerter.

        Args:
            config: Configuração com alertmanager_url, slack_webhook, etc.
        """
        self.config = config
        self.alertmanager_url = config.get("alertmanager_url")
        self.slack_webhook = config.get("slack_webhook_url")
        self.enable_alerts = config.get("enable_drift_alerts", True)

        logger.info(
            "DriftAlerter initialized",
            alertmanager_configured=bool(self.alertmanager_url),
            slack_configured=bool(self.slack_webhook),
        )

    async def send_alert(
        self, drift_score: float, drifted_features: List[str], report: Dict[str, Any]
    ):
        """
        Envia alerta de drift.

        Args:
            drift_score: Score de drift (PSI)
            drifted_features: Lista de features com drift
            report: Relatório completo de drift
        """
        if not self.enable_alerts:
            logger.debug("Alerts disabled, skipping")
            return

        alert_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "severity": self._calculate_severity(drift_score),
            "drift_score": drift_score,
            "num_drifted_features": len(drifted_features),
            "drifted_features": drifted_features[:10],  # Limitar a 10
            "message": self._generate_alert_message(drift_score, drifted_features),
        }

        # Enviar para Alertmanager
        if self.alertmanager_url:
            await self._send_to_alertmanager(alert_data)

        # Enviar para Slack
        if self.slack_webhook:
            await self._send_to_slack(alert_data)

        logger.info(
            "Drift alert sent", severity=alert_data["severity"], drift_score=drift_score
        )

    def _calculate_severity(self, drift_score: float) -> str:
        """Calcula severidade do alerta baseado no score."""
        if drift_score > 0.5:
            return "critical"
        elif drift_score > 0.3:
            return "warning"
        else:
            return "info"

    def _generate_alert_message(
        self, drift_score: float, drifted_features: List[str]
    ) -> str:
        """Gera mensagem de alerta."""
        return (
            f"🚨 Drift detectado nos especialistas neurais!\n"
            f"Score de drift: {drift_score:.3f}\n"
            f"Features afetadas ({len(drifted_features)}): {', '.join(drifted_features[:5])}\n"
            f"Ação recomendada: Revisar modelos e considerar re-treinamento."
        )

    async def _send_to_alertmanager(self, alert_data: Dict[str, Any]):
        """Envia alerta para Prometheus Alertmanager."""
        try:
            alert_payload = [
                {
                    "labels": {
                        "alertname": "ModelDriftDetected",
                        "severity": alert_data["severity"],
                        "service": "neural-hive-specialists",
                    },
                    "annotations": {
                        "summary": alert_data["message"],
                        "drift_score": str(alert_data["drift_score"]),
                        "num_drifted_features": str(alert_data["num_drifted_features"]),
                    },
                    "startsAt": alert_data["timestamp"],
                }
            ]

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.alertmanager_url}/api/v1/alerts",
                    json=alert_payload,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status == 200:
                        logger.debug("Alert sent to Alertmanager")
                    else:
                        logger.warning(
                            "Failed to send alert to Alertmanager",
                            status=response.status,
                        )

        except Exception as e:
            logger.error("Error sending alert to Alertmanager", error=str(e))

    async def _send_to_slack(self, alert_data: Dict[str, Any]):
        """Envia alerta para Slack."""
        try:
            # Mapear severidade para cor
            color_map = {"critical": "#FF0000", "warning": "#FFA500", "info": "#0000FF"}

            slack_payload = {
                "attachments": [
                    {
                        "color": color_map.get(alert_data["severity"], "#808080"),
                        "title": "🚨 Model Drift Detected",
                        "text": alert_data["message"],
                        "fields": [
                            {
                                "title": "Drift Score",
                                "value": f"{alert_data['drift_score']:.3f}",
                                "short": True,
                            },
                            {
                                "title": "Affected Features",
                                "value": str(alert_data["num_drifted_features"]),
                                "short": True,
                            },
                            {
                                "title": "Severity",
                                "value": alert_data["severity"].upper(),
                                "short": True,
                            },
                        ],
                        "footer": "Neural Hive Specialists",
                        "ts": int(datetime.utcnow().timestamp()),
                    }
                ]
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.slack_webhook,
                    json=slack_payload,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status == 200:
                        logger.debug("Alert sent to Slack")
                    else:
                        logger.warning(
                            "Failed to send alert to Slack", status=response.status
                        )

        except Exception as e:
            logger.error("Error sending alert to Slack", error=str(e))
