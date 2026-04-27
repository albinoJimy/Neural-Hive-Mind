"""
Cliente PagerDuty para envio de eventos via Events API v2.
"""

from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)


class PagerDutyEvent:
    """Modelo de evento PagerDuty."""

    routing_key: str
    event_action: str
    payload: dict[str, Any]
    dedup_key: str | None = None

    def __init__(
        self,
        routing_key: str,
        event_action: str = "trigger",
        payload: dict[str, Any] | None = None,
        dedup_key: str | None = None,
    ):
        self.routing_key = routing_key
        self.event_action = event_action
        self.payload = payload or {}
        self.dedup_key = dedup_key


class PagerDutyClient:
    """
    Cliente PagerDuty para envio de eventos via Events API v2.

    Features:
    - Trigger, acknowledge e resolve alerts
    - Suporte para custom details
    - Retry automático com tenacity
    - Dedup keys para evitar duplicação

    Docs: https://developer.pagerduty.com/docs/ZG9jOjExMDI5NTgw-events-api-v2-overview
    """

    DEFAULT_API_URL = "https://events.pagerduty.com/v2/enqueue"

    def __init__(
        self,
        routing_key: str | None = None,
        api_url: str = DEFAULT_API_URL,
        timeout_seconds: int = 30,
        max_retries: int = 3,
    ):
        """
        Inicializa cliente PagerDuty.

        Args:
            routing_key: Integration/Routing key do PagerDuty
            api_url: URL da Events API v2
            timeout_seconds: Timeout para requests HTTP
            max_retries: Número máximo de retries
        """
        self.routing_key = routing_key
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.session: httpx.AsyncClient | None = None
        self.logger = logger

    async def connect(self):
        """Inicializa cliente HTTP."""
        self.session = httpx.AsyncClient(timeout=self.timeout_seconds)
        self.logger.info("pagerduty_client_connected")

    async def disconnect(self):
        """Fecha cliente HTTP."""
        if self.session:
            await self.session.aclose()
            self.session = None
            self.logger.info("pagerduty_client_disconnected")

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def trigger_alert(
        self,
        dedup_key: str,
        summary: str,
        severity: str,
        source: str,
        timestamp: str | None = None,
        custom_details: dict[str, Any] | None = None,
    ) -> bool:
        """
        Envia evento de trigger para PagerDuty.

        Args:
            dedup_key: Chave única para deduplicação (geralmente alert_id)
            summary: Sumário do alerta
            severity: Severidade (critical, error, warning, info)
            source: Fonte do alerta (nome do serviço)
            timestamp: Timestamp ISO 8601 (opcional, usa UTC agora se não fornecido)
            custom_details: Detalhes customizados do alerta

        Returns:
            True se enviado com sucesso

        Raises:
            ValueError: Se routing_key não está configurado
            httpx.HTTPError: Se erro HTTP após retries
        """
        if not self.routing_key:
            raise ValueError("PagerDuty routing key is required")

        if not self.session:
            await self.connect()

        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()

        payload = {
            "routing_key": self.routing_key,
            "event_action": "trigger",
            "payload": {
                "summary": summary,
                "severity": self._map_severity(severity),
                "source": source,
                "timestamp": timestamp,
            },
            "dedup_key": dedup_key,
        }

        if custom_details:
            payload["payload"]["custom_details"] = custom_details

        try:
            response = await self.session.post(self.api_url, json=payload)
            response.raise_for_status()

            self.logger.info(
                "pagerduty_alert_triggered",
                dedup_key=dedup_key,
                status_code=response.status_code,
                summary=summary,
            )
            return True

        except httpx.HTTPStatusError as e:
            self.logger.error(
                "pagerduty_http_error",
                status_code=e.response.status_code,
                error=str(e),
            )
            raise

        except Exception as e:
            self.logger.error("pagerduty_trigger_failed", error=str(e))
            raise

    async def acknowledge_alert(self, dedup_key: str) -> bool:
        """
        Acknowledge alerta existente no PagerDuty.

        Args:
            dedup_key: Dedup key do alerta a acknowledge

        Returns:
            True se enviado com sucesso
        """
        if not self.routing_key:
            raise ValueError("PagerDuty routing key is required")

        if not self.session:
            await self.connect()

        payload = {
            "routing_key": self.routing_key,
            "event_action": "acknowledge",
            "dedup_key": dedup_key,
        }

        try:
            response = await self.session.post(self.api_url, json=payload)
            response.raise_for_status()

            self.logger.info(
                "pagerduty_alert_acknowledged",
                dedup_key=dedup_key,
                status_code=response.status_code,
            )
            return True

        except Exception as e:
            self.logger.error("pagerduty_acknowledge_failed", error=str(e))
            raise

    async def resolve_alert(self, dedup_key: str) -> bool:
        """
        Resolve alerta existente no PagerDuty.

        Args:
            dedup_key: Dedup key do alerta a resolver

        Returns:
            True se enviado com sucesso
        """
        if not self.routing_key:
            raise ValueError("PagerDuty routing key is required")

        if not self.session:
            await self.connect()

        payload = {
            "routing_key": self.routing_key,
            "event_action": "resolve",
            "dedup_key": dedup_key,
        }

        try:
            response = await self.session.post(self.api_url, json=payload)
            response.raise_for_status()

            self.logger.info(
                "pagerduty_alert_resolved",
                dedup_key=dedup_key,
                status_code=response.status_code,
            )
            return True

        except Exception as e:
            self.logger.error("pagerduty_resolve_failed", error=str(e))
            raise

    async def send_sla_alert(
        self,
        alert_id: str,
        severity: str,
        title: str,
        message: str,
        service_name: str | None = None,
        slo_id: str | None = None,
        error_budget_remaining: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> bool:
        """
        Envia alerta SLA formatado para PagerDuty.

        Args:
            alert_id: ID do alerta (usado como dedup_key)
            severity: Severidade (critical, warning, info, emergency)
            title: Título do alerta
            message: Mensagem do alerta
            service_name: Nome do serviço (source)
            slo_id: ID do SLO
            error_budget_remaining: Error budget restante (%)
            details: Detalhes adicionais

        Returns:
            True se enviado com sucesso
        """
        # Preparar custom details
        custom_details = {
            "message": message,
        }

        if slo_id:
            custom_details["slo_id"] = slo_id

        if error_budget_remaining is not None:
            custom_details["error_budget_remaining_percent"] = error_budget_remaining

        if details:
            custom_details.update(details)

        return await self.trigger_alert(
            dedup_key=alert_id,
            summary=title,
            severity=severity,
            source=service_name or "sla-management-system",
            custom_details=custom_details,
        )

    def _map_severity(self, severity: str) -> str:
        """
        Mapeia severidade interna para PagerDuty severity.

        PagerDuty severities: critical, error, warning, info

        Args:
            severity: Severidade interna

        Returns:
            Severidade formatada para PagerDuty
        """
        severity_mapping = {
            "emergency": "critical",
            "critical": "critical",
            "error": "error",
            "warning": "warning",
            "info": "info",
        }
        return severity_mapping.get(severity.lower(), "info")

    async def health_check(self) -> bool:
        """Verifica se cliente está saudável."""
        return self.session is not None and self.routing_key is not None
