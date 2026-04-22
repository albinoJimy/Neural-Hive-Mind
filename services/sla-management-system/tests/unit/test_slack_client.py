"""
Testes unitários para SlackClient.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.clients.slack_client import SlackClient, SlackMessage


@pytest.fixture()
def slack_webhook_url():
    """Webhook URL para testes."""
    return "https://hooks.slack.com/services/TEST/TEST/TEST"


@pytest.fixture()
def slack_client(slack_webhook_url):
    """Cliente Slack para testes."""
    return SlackClient(webhook_url=slack_webhook_url)


class TestSlackClient:
    """Testes para SlackClient."""

    @pytest.mark.asyncio()
    async def test_send_message_simple(self, slack_client):
        """Testa envio de mensagem simples."""
        # Setup
        slack_client.session = AsyncMock()
        response_mock = MagicMock()
        response_mock.status_code = 200
        response_mock.raise_for_status = MagicMock()
        slack_client.session.post.return_value = response_mock

        # Act
        result = await slack_client.send_message("Test message")

        # Assert
        assert result is True
        slack_client.session.post.assert_called_once()
        call_args = slack_client.session.post.call_args
        assert call_args.kwargs["json"]["text"] == "Test message"

    @pytest.mark.asyncio()
    async def test_send_message_with_blocks(self, slack_client):
        """Testa envio de mensagem com blocks."""
        # Setup
        slack_client.session = AsyncMock()
        response_mock = MagicMock()
        response_mock.status_code = 200
        slack_client.session.post.return_value = response_mock

        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "Test block"},
            }
        ]

        # Act
        result = await slack_client.send_message(
            message="Fallback text",
            blocks=blocks,
        )

        # Assert
        assert result is True
        call_args = slack_client.session.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["blocks"] == blocks

    @pytest.mark.asyncio()
    async def test_send_message_with_attachments(self, slack_client):
        """Testa envio de mensagem com attachments."""
        # Setup
        slack_client.session = AsyncMock()
        response_mock = MagicMock()
        response_mock.status_code = 200
        slack_client.session.post.return_value = response_mock

        attachments = [{"color": "#FF0000", "text": "Error"}]

        # Act
        result = await slack_client.send_message(
            message="Test",
            attachments=attachments,
        )

        # Assert
        assert result is True
        call_args = slack_client.session.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["attachments"] == attachments

    @pytest.mark.asyncio()
    async def test_send_message_http_error(self, slack_client):
        """Testa retry em caso de erro HTTP."""
        # Setup - criar HTTPStatusError real que será retry pelo tenacity
        import httpx

        slack_client.session = AsyncMock()
        response_mock = MagicMock()
        response_mock.status_code = 500
        http_error = httpx.HTTPStatusError("500 Error", request=MagicMock(), response=response_mock)
        slack_client.session.post.side_effect = http_error

        # Act & Assert - após 3 retries, erro deve ser lançado
        with pytest.raises(httpx.HTTPStatusError):
            await slack_client.send_message("Test")

    @pytest.mark.asyncio()
    async def test_send_message_no_webhook_url(self):
        """Testa erro quando não há webhook URL."""
        # Setup
        client = SlackClient(webhook_url=None)

        # Act & Assert
        with pytest.raises(ValueError, match="Slack webhook URL is required"):
            await client.send_message("Test")

    @pytest.mark.asyncio()
    async def test_send_sla_alert_message(self, slack_client):
        """Testa formatação de alerta SLA."""
        # Setup
        slack_client.session = AsyncMock()
        response_mock = MagicMock()
        response_mock.status_code = 200
        slack_client.session.post.return_value = response_mock

        alert_data = {
            "alert_id": "test-123",
            "severity": "critical",
            "title": "SLA Violation",
            "message": "Error budget exceeded",
            "service_name": "api-gateway",
            "slo_id": "slo-1",
            "error_budget_remaining": 15.5,
        }

        # Act
        result = await slack_client.send_sla_alert(**alert_data)

        # Assert
        assert result is True
        call_args = slack_client.session.post.call_args
        payload = call_args.kwargs["json"]

        # Verificar estrutura da mensagem
        blocks = payload.get("blocks", [])
        assert len(blocks) > 0
        assert any("SLA Violation" in str(block) for block in blocks)

    @pytest.mark.asyncio()
    async def test_connect_and_disconnect(self, slack_client):
        """Testa conexão e desconexão."""
        # Act - Connect
        await slack_client.connect()
        assert slack_client.session is not None

        # Act - Disconnect
        await slack_client.disconnect()
        assert slack_client.session is None

    @pytest.mark.asyncio()
    async def test_send_message_with_custom_channel(self, slack_client):
        """Testa envio para canal customizado."""
        # Setup
        slack_client.session = AsyncMock()
        response_mock = MagicMock()
        response_mock.status_code = 200
        slack_client.session.post.return_value = response_mock

        # Act
        result = await slack_client.send_message(
            message="Test",
            channel="#custom-channel",
        )

        # Assert
        assert result is True
        # A mensagem deve incluir o canal se implementado

    def test_color_for_severity_critical(self, slack_client):
        """Testa mapeamento de cor para severidade critical."""
        color = slack_client._get_color_for_severity("critical")
        assert color == "#FF6600"

    def test_color_for_severity_warning(self, slack_client):
        """Testa mapeamento de cor para severidade warning."""
        color = slack_client._get_color_for_severity("warning")
        assert color == "#FFCC00"

    def test_color_for_severity_info(self, slack_client):
        """Testa mapeamento de cor para severidade info."""
        color = slack_client._get_color_for_severity("info")
        assert color == "#36A64F"

    def test_color_for_severity_emergency(self, slack_client):
        """Testa mapeamento de cor para severidade emergency."""
        color = slack_client._get_color_for_severity("emergency")
        assert color == "#FF0000"


class TestSlackMessage:
    """Testes para modelo SlackMessage."""

    def test_create_slack_message(self):
        """Testa criação de mensagem Slack."""
        message = SlackMessage(
            webhook_url="https://hooks.slack.com/services/T/B/X",
            text="Test message",
        )
        assert message.webhook_url == "https://hooks.slack.com/services/T/B/X"
        assert message.text == "Test message"

    def test_create_slack_message_with_blocks(self):
        """Testa criação de mensagem com blocks."""
        blocks = [{"type": "section", "text": {"type": "plain_text", "text": "Test"}}]
        message = SlackMessage(
            webhook_url="https://hooks.slack.com/services/T/B/X",
            text="Fallback",
            blocks=blocks,
        )
        assert message.blocks == blocks
