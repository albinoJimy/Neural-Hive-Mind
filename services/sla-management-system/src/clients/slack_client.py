"""
Cliente Slack para envio de notificações via webhook.
"""

from datetime import UTC, datetime
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


class SlackMessage:
    """Modelo de mensagem Slack."""

    webhook_url: str
    text: str
    blocks: list[dict[str, Any]] | None = None
    attachments: list[dict[str, Any]] | None = None
    channel: str | None = None

    def __init__(
        self,
        webhook_url: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        channel: str | None = None,
    ):
        self.webhook_url = webhook_url
        self.text = text
        self.blocks = blocks
        self.attachments = attachments
        self.channel = channel


class SlackClient:
    """
    Cliente Slack para envio de mensagens via Incoming Webhooks.

    Features:
    - Envio de mensagens simples
    - Suporte para blocks (rich formatting)
    - Suporte para attachments (color coding)
    - Retry automático com tenacity
    - Timeout configurável
    """

    def __init__(
        self,
        webhook_url: str | None = None,
        timeout_seconds: int = 30,
        max_retries: int = 3,
    ):
        """
        Inicializa cliente Slack.

        Args:
            webhook_url: URL do Incoming Webhook
            timeout_seconds: Timeout para requests HTTP
            max_retries: Número máximo de retries
        """
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.session: httpx.AsyncClient | None = None
        self.logger = logger

    async def connect(self):
        """Inicializa cliente HTTP."""
        self.session = httpx.AsyncClient(timeout=self.timeout_seconds)
        self.logger.info("slack_client_connected")

    async def disconnect(self):
        """Fecha cliente HTTP."""
        if self.session:
            await self.session.aclose()
            self.session = None
            self.logger.info("slack_client_disconnected")

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def send_message(
        self,
        message: str,
        blocks: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        channel: str | None = None,
    ) -> bool:
        """
        Envia mensagem para Slack via webhook.

        Args:
            message: Texto da mensagem (fallback)
            blocks: Lista de blocks para formatação rica
            attachments: Lista de attachments (cores, etc)
            channel: Canal override (opcional)

        Returns:
            True se enviado com sucesso, False caso contrário

        Raises:
            ValueError: Se webhook_url não está configurado
            httpx.HTTPError: Se erro HTTP após retries
        """
        if not self.webhook_url:
            raise ValueError("Slack webhook URL is required")

        if not self.session:
            await self.connect()

        # Construir payload
        payload: dict[str, Any] = {"text": message}

        if blocks:
            payload["blocks"] = blocks

        if attachments:
            payload["attachments"] = attachments

        if channel:
            payload["channel"] = channel

        try:
            response = await self.session.post(self.webhook_url, json=payload)
            response.raise_for_status()

            self.logger.info(
                "slack_message_sent",
                status_code=response.status_code,
                message_length=len(message),
            )
            return True

        except httpx.HTTPStatusError as e:
            self.logger.error(
                "slack_http_error",
                status_code=e.response.status_code,
                error=str(e),
            )
            raise

        except Exception as e:
            self.logger.error("slack_send_failed", error=str(e))
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
        Envia alerta SLA formatado para Slack.

        Args:
            alert_id: ID do alerta
            severity: Severidade (critical, warning, info, emergency)
            title: Título do alerta
            message: Mensagem do alerta
            service_name: Nome do serviço
            slo_id: ID do SLO
            error_budget_remaining: Error budget restante (%)
            details: Detalhes adicionais

        Returns:
            True se enviado com sucesso
        """
        # Determinar emoji e cor
        emoji = self._get_emoji_for_severity(severity)
        color = self._get_color_for_severity(severity)

        # Construir blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {title}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Severity:*\n{severity.upper()}"},
                    {"type": "mrkdwn", "text": f"*Service:*\n{service_name or 'N/A'}"},
                    {"type": "mrkdwn", "text": f"*SLO ID:*\n{slo_id or 'N/A'}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Triggered:*\n{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                    },
                ],
            },
        ]

        # Adicionar error budget se disponível
        if error_budget_remaining is not None:
            blocks.append(
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Error Budget:*\n{error_budget_remaining:.1f}%",
                        }
                    ],
                }
            )

        # Adicionar mensagem
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Message:*\n{message}"},
            }
        )

        # Adicionar detalhes se existirem
        if details:
            details_text = "\n".join([f"• *{k}*: {v}" for k, v in details.items()])
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Details:*\n{details_text}"},
                }
            )

        # Adicionar footer com alert_id
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Alert ID: `{alert_id}` | SLA Management System",
                    }
                ],
            }
        )

        # Adicionar attachment com cor
        attachments = [{"color": color}] if color else None

        return await self.send_message(
            message=title,
            blocks=blocks,
            attachments=attachments,
        )

    def _get_emoji_for_severity(self, severity: str) -> str:
        """Retorna emoji para severidade."""
        emojis = {
            "emergency": ":rotating_light:",
            "critical": ":warning:",
            "warning": ":large_orange_diamond:",
            "info": ":information_source:",
        }
        return emojis.get(severity.lower(), ":white_circle:")

    def _get_color_for_severity(self, severity: str) -> str:
        """Retorna cor para Slack baseado na severidade."""
        colors = {
            "emergency": "#FF0000",  # Vermelho
            "critical": "#FF6600",  # Laranja
            "warning": "#FFCC00",  # Amarelo
            "info": "#36A64F",  # Verde
        }
        return colors.get(severity.lower(), "#36A64F")

    def _should_retry(self, exception: Exception) -> bool:
        """Determina se exception deve ser retry."""
        return isinstance(exception, (httpx.HTTPError, httpx.TimeoutException))

    async def health_check(self) -> bool:
        """Verifica se cliente está saudável."""
        return self.session is not None and self.webhook_url is not None
