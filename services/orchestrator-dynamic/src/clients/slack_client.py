"""
Slack Client para envio de notificações ao Slack via webhook.

Este cliente envia mensagens para canais Slack usando Incoming Webhooks.
"""
import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class SlackClient:
    """Cliente para enviar mensagens ao Slack via webhook."""

    def __init__(self, webhook_url: str | None = None):
        """
        Inicializa o cliente Slack.

        Args:
            webhook_url: URL do webhook Slack (opcional - usa settings se não fornecido)
        """
        config = get_settings()
        self.webhook_url = webhook_url or getattr(config, "slack_webhook_url", "")
        self.logger = logger
        self.client = httpx.AsyncClient(timeout=10.0)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
    )
    async def send_message(
        self,
        text: str,
        channel: str | None = None,
        blocks: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Envia mensagem para o Slack.

        Args:
            text: Texto principal da mensagem (fallback)
            channel: Canal específico (opcional, usa default do webhook)
            blocks: Blocos estruturados (opcional)

        Returns:
            Resposta do Slack em formato dict

        Raises:
            httpx.HTTPError: Se o envio falhar após retries
        """
        if not self.webhook_url:
            self.logger.warning("Slack webhook URL not configured, skipping")
            return {}

        payload: dict[str, Any] = {"text": text}
        if channel:
            payload["channel"] = channel
        if blocks:
            payload["blocks"] = blocks

        try:
            response = await self.client.post(self.webhook_url, json=payload)
            response.raise_for_status()

            self.logger.info(
                "slack_message_sent",
                channel=channel or "default",
                status_code=response.status_code,
            )
            return response.json()
        except httpx.HTTPStatusError as e:
            self.logger.error(
                "slack_http_error",
                status_code=e.response.status_code,
                response_text=e.response.text,
            )
            raise
        except Exception as e:
            self.logger.error("slack_send_error", error=str(e))
            raise

    async def close(self):
        """Fecha o cliente HTTP."""
        await self.client.aclose()

    def is_configured(self) -> bool:
        """Verifica se o cliente está configurado."""
        return bool(self.webhook_url)
