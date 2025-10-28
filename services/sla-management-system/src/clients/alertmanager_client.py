"""
Cliente para Alertmanager API.
"""

from typing import List, Dict, Any, Optional
import httpx
import structlog

from ..config.settings import AlertmanagerSettings


class AlertmanagerClient:
    """Cliente para Alertmanager API."""

    def __init__(self, settings: AlertmanagerSettings):
        self.base_url = settings.url
        self.timeout = settings.api_timeout_seconds
        self.session: Optional[httpx.AsyncClient] = None
        self.logger = structlog.get_logger(__name__)

    async def connect(self):
        """Inicializa cliente HTTP."""
        self.session = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout
        )
        self.logger.info("alertmanager_client_connected", base_url=self.base_url)

    async def disconnect(self):
        """Fecha cliente HTTP."""
        if self.session:
            await self.session.aclose()
            self.logger.info("alertmanager_client_disconnected")

    async def get_alerts(
        self,
        filters: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """Busca alertas ativos."""
        try:
            params = {}
            if filters:
                # Converte filtros para formato Alertmanager
                filter_list = [f'{k}="{v}"' for k, v in filters.items()]
                params["filter"] = filter_list

            response = await self.session.get("/api/v2/alerts", params=params)
            response.raise_for_status()

            alerts = response.json()
            self.logger.debug("alerts_fetched", count=len(alerts))
            return alerts

        except Exception as e:
            self.logger.error("alerts_fetch_failed", error=str(e))
            return []

    async def get_slo_alerts(self) -> List[Dict[str, Any]]:
        """Busca apenas alertas relacionados a SLOs."""
        try:
            # Filtro para alertas com label slo
            response = await self.session.get(
                "/api/v2/alerts",
                params={"filter": ['slo=~".+"']}
            )
            response.raise_for_status()

            alerts = response.json()
            self.logger.debug("slo_alerts_fetched", count=len(alerts))
            return alerts

        except Exception as e:
            self.logger.error("slo_alerts_fetch_failed", error=str(e))
            return []

    async def silence_alert(
        self,
        alert_id: str,
        duration_hours: int,
        comment: str
    ) -> str:
        """Cria silence para um alerta."""
        try:
            from datetime import datetime, timedelta

            now = datetime.utcnow()
            ends_at = now + timedelta(hours=duration_hours)

            silence_data = {
                "matchers": [{"name": "alertname", "value": alert_id, "isRegex": False}],
                "startsAt": now.isoformat() + "Z",
                "endsAt": ends_at.isoformat() + "Z",
                "comment": comment,
                "createdBy": "sla-management-system"
            }

            response = await self.session.post("/api/v2/silences", json=silence_data)
            response.raise_for_status()

            result = response.json()
            silence_id = result.get("silenceID", "")

            self.logger.info(
                "alert_silenced",
                alert_id=alert_id,
                silence_id=silence_id,
                duration_hours=duration_hours
            )
            return silence_id

        except Exception as e:
            self.logger.error("alert_silence_failed", alert_id=alert_id, error=str(e))
            return ""

    async def delete_silence(self, silence_id: str) -> bool:
        """Remove silence."""
        try:
            response = await self.session.delete(f"/api/v2/silence/{silence_id}")
            response.raise_for_status()

            self.logger.info("silence_deleted", silence_id=silence_id)
            return True

        except Exception as e:
            self.logger.error("silence_deletion_failed", silence_id=silence_id, error=str(e))
            return False

    async def health_check(self) -> bool:
        """Verifica conectividade."""
        try:
            response = await self.session.get("/-/healthy")
            return response.status_code == 200
        except Exception as e:
            self.logger.error("alertmanager_health_check_failed", error=str(e))
            return False
