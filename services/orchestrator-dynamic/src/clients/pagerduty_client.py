"""
PagerDuty Client para envio de alertas via Events API v2.

Este cliente envia alertas para o PagerDuty usando a Events API v2,
permitindo trigger, acknowledge e resolve de incidentes.
"""

import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class PagerDutyClient:
    """
    Cliente para Events API v2 do PagerDuty.

    Docs: https://developer.pagerduty.com/docs/ZG9jQmR1kv5nQ3mCZvGGw/Events-API_v2/overview
    """

    API_URL = "https://events.pagerduty.com/v2/enqueue"

    def __init__(self, routing_key: str | None = None):
        """
        Inicializa o cliente PagerDuty.

        Args:
            routing_key: Routing Key da integração PagerDuty (opcional - usa settings se não fornecido)
        """
        config = get_settings()
        self.routing_key = routing_key or getattr(config, "pagerduty_routing_key", "")
        self.logger = logger
        self.client = httpx.AsyncClient(timeout=10.0)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
    )
    async def trigger_alert(
        self,
        dedup_key: str,
        event_type: str = "trigger",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Envia alerta para o PagerDuty.

        Args:
            dedup_key: Chave única para deduplicação (incident ID)
            event_type: Tipo do evento ("trigger", "acknowledge", "resolve")
            payload: Payload com detalhes do alerta

        Returns:
            Resposta do PagerDuty em formato dict

        Raises:
            httpx.HTTPError: Se o envio falhar após retries
        """
        if not self.routing_key:
            self.logger.warning("PagerDuty routing key not configured, skipping")
            return {}

        request_payload: dict[str, Any] = {
            "routing_key": self.routing_key,
            "event_action": event_type,
            "dedup_key": dedup_key,
        }

        if payload is not None:
            request_payload["payload"] = payload

        try:
            response = await self.client.post(self.API_URL, json=request_payload)
            response.raise_for_status()

            self.logger.info(
                "pagerduty_alert_sent",
                dedup_key=dedup_key,
                event_type=event_type,
                status_code=response.status_code,
            )
            return response.json()
        except httpx.HTTPStatusError as e:
            self.logger.error(
                "pagerduty_http_error",
                status_code=e.response.status_code,
                response_text=e.response.text,
            )
            raise
        except Exception as e:
            self.logger.error("pagerduty_send_error", error=str(e))
            raise

    async def acknowledge_alert(self, dedup_key: str) -> dict[str, Any]:
        """
        Acknowledge um alerta existente.

        Args:
            dedup_key: Chave única do alerta

        Returns:
            Resposta do PagerDuty em formato dict
        """
        return await self.trigger_alert(dedup_key, event_type="acknowledge")

    async def resolve_alert(self, dedup_key: str) -> dict[str, Any]:
        """
        Resolve um alerta existente.

        Args:
            dedup_key: Chave única do alerta

        Returns:
            Resposta do PagerDuty em formato dict
        """
        return await self.trigger_alert(dedup_key, event_type="resolve")

    async def close(self):
        """Fecha o cliente HTTP."""
        await self.client.aclose()

    def is_configured(self) -> bool:
        """Verifica se o cliente está configurado."""
        return bool(self.routing_key)
