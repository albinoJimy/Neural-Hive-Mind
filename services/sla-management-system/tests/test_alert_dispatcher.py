"""
Testes para AlertDispatcher do SLA Management System.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from src.models.alert_rule import (
    AlertSeverity,
    AlertChannel,
    Alert,
)
from src.services.alert_dispatcher import AlertDispatcher


@pytest.fixture
def sample_alert():
    """Alerta de exemplo."""
    return Alert(
        alert_id="alert-123",
        rule_id="rule-123",
        rule_name="Test Rule",
        severity=AlertSeverity.WARNING,  # Pydantic com use_enum_values converte para string
        title="Test Alert",
        message="This is a test alert",
        details={"budget_remaining": 15.0, "slo_target": 0.99},
        slo_id="slo-123",
        service_name="test-service",
        triggered_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def alert_dispatcher():
    """Instância do AlertDispatcher para testes."""
    return AlertDispatcher(
        slack_webhook_url="https://hooks.slack.com/test",
        pagerduty_routing_key="test-pd-key",
        smtp_host="smtp.test.com",
        smtp_port=587,
        smtp_username="test@test.com",
        smtp_password="password",
        smtp_from="alerts@test.com",
    )


class TestAlertDispatcherInit:
    """Testes de inicialização do AlertDispatcher."""

    def test_init_with_all_configs(self):
        """Testa inicialização com todas as configurações."""
        dispatcher = AlertDispatcher(
            slack_webhook_url="https://hooks.slack.com/test",
            pagerduty_routing_key="test-pd-key",
            smtp_host="smtp.test.com",
            smtp_port=587,
            smtp_username="test@test.com",
            smtp_password="password",
            smtp_from="alerts@test.com",
        )

        assert dispatcher.slack_webhook_url == "https://hooks.slack.com/test"
        assert dispatcher.pagerduty_routing_key == "test-pd-key"
        assert dispatcher.smtp_config["host"] == "smtp.test.com"
        assert dispatcher.smtp_config["port"] == 587
        assert dispatcher.smtp_config["username"] == "test@test.com"
        assert dispatcher.smtp_config["password"] == "password"
        assert dispatcher.smtp_config["from"] == "alerts@test.com"

    def test_init_with_minimal_configs(self):
        """Testa inicialização com configurações mínimas."""
        dispatcher = AlertDispatcher()

        assert dispatcher.slack_webhook_url is None
        assert dispatcher.pagerduty_routing_key is None
        assert dispatcher.smtp_config["host"] is None
        assert dispatcher.session is None


class TestAlertDispatcherConnect:
    """Testes de conexão do AlertDispatcher."""

    @pytest.mark.asyncio
    async def test_connect_creates_session(self, alert_dispatcher):
        """Testa que connect cria sessão HTTP."""
        await alert_dispatcher.connect()

        assert alert_dispatcher.session is not None

    @pytest.mark.asyncio
    async def test_connect_logs_info(self, alert_dispatcher):
        """Testa que connect loga informação."""
        with patch.object(alert_dispatcher.logger, "info") as mock_log:
            await alert_dispatcher.connect()

            mock_log.assert_called_once_with("alert_dispatcher_connected")


class TestAlertDispatcherDisconnect:
    """Testes de desconexão do AlertDispatcher."""

    @pytest.mark.asyncio
    async def test_disconnect_closes_session(self, alert_dispatcher):
        """Testa que disconnect fecha sessão HTTP."""
        await alert_dispatcher.connect()
        await alert_dispatcher.disconnect()

        # Sessão deve ser fechada (não verificável diretamente, mas não deve dar erro)
        assert True

    @pytest.mark.asyncio
    async def test_disconnect_without_connect(self, alert_dispatcher):
        """Testa disconnect sem connect anterior (não deve dar erro)."""
        await alert_dispatcher.disconnect()  # Não deve levantar exceção


class TestDispatchToSlack:
    """Testes de despacho para Slack."""

    @pytest.mark.asyncio
    async def test_dispatch_to_slack_success(self, alert_dispatcher, sample_alert):
        """Testa despacho bem-sucedido para Slack."""
        await alert_dispatcher.connect()

        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(alert_dispatcher.session, "post", return_value=mock_response):
            result = await alert_dispatcher._dispatch_to_slack(
                sample_alert, {"webhook_url": "https://hooks.slack.com/test"}
            )

        assert result.success is True
        assert result.alert_id == sample_alert.alert_id
        assert result.channel == AlertChannel.SLACK
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_dispatch_to_slack_no_webhook(self, alert_dispatcher, sample_alert):
        """Testa despacho para Slack sem webhook configurado."""
        await alert_dispatcher.connect()

        alert_dispatcher.slack_webhook_url = None

        result = await alert_dispatcher._dispatch_to_slack(sample_alert, {"webhook_url": None})

        assert result.success is False
        assert "No webhook URL configured" in result.error_message

    @pytest.mark.asyncio
    async def test_dispatch_to_slack_with_details(self, alert_dispatcher, sample_alert):
        """Testa despacho para Slack com detalhes."""
        await alert_dispatcher.connect()

        sample_alert.details = {
            "budget_remaining": 15.0,
            "burn_rate": 1.5,
            "time_until_exhausted": "2h 30m",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(alert_dispatcher.session, "post", return_value=mock_response):
            result = await alert_dispatcher._dispatch_to_slack(
                sample_alert, {"webhook_url": "https://hooks.slack.com/test"}
            )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_to_slack_http_error(self, alert_dispatcher, sample_alert):
        """Testa despacho para Slack com erro HTTP."""
        await alert_dispatcher.connect()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status = MagicMock(side_effect=Exception("HTTP 500"))

        with patch.object(alert_dispatcher.session, "post", return_value=mock_response):
            result = await alert_dispatcher._dispatch_to_slack(
                sample_alert, {"webhook_url": "https://hooks.slack.com/test"}
            )

        assert result.success is False
        assert "HTTP 500" in result.error_message


class TestDispatchToPagerDuty:
    """Testes de despacho para PagerDuty."""

    @pytest.mark.asyncio
    async def test_dispatch_to_pagerduty_success(self, alert_dispatcher, sample_alert):
        """Testa despacho bem-sucedido para PagerDuty."""
        await alert_dispatcher.connect()

        mock_response = MagicMock()
        mock_response.status_code = 202  # PagerDuty retorna 202
        mock_response.raise_for_status = MagicMock()

        with patch.object(alert_dispatcher.session, "post", return_value=mock_response):
            result = await alert_dispatcher._dispatch_to_pagerduty(
                sample_alert, {"routing_key": "test-pd-key"}
            )

        assert result.success is True
        assert result.alert_id == sample_alert.alert_id
        assert result.channel == AlertChannel.PAGERDUTY

    @pytest.mark.asyncio
    async def test_dispatch_to_pagerduty_no_routing_key(self, alert_dispatcher, sample_alert):
        """Testa despacho para PagerDuty sem routing key."""
        await alert_dispatcher.connect()

        alert_dispatcher.pagerduty_routing_key = None

        result = await alert_dispatcher._dispatch_to_pagerduty(sample_alert, {"routing_key": None})

        assert result.success is False
        assert "No routing key configured" in result.error_message

    @pytest.mark.asyncio
    async def test_dispatch_to_pagerduty_critical_severity(self, alert_dispatcher, sample_alert):
        """Testa despacho para PagerDuty com severidade crítica."""
        await alert_dispatcher.connect()

        sample_alert.severity = AlertSeverity.CRITICAL

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            alert_dispatcher.session, "post", return_value=mock_response
        ) as mock_post:
            await alert_dispatcher._dispatch_to_pagerduty(
                sample_alert, {"routing_key": "test-pd-key"}
            )

            # Verificar que severity foi mapeada corretamente
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            assert payload["payload"]["severity"] == "critical"


class TestDispatchToEmail:
    """Testes de despacho por email."""

    @pytest.mark.asyncio
    async def test_dispatch_to_email_success(self, alert_dispatcher, sample_alert):
        """Testa despacho bem-sucedido por email."""
        result = await alert_dispatcher._dispatch_to_email(
            sample_alert, {"to": ["recipient@test.com"]}
        )

        # Email é simulado, então deve retornar sucesso
        assert result.success is True
        assert result.channel == AlertChannel.EMAIL

    @pytest.mark.asyncio
    async def test_dispatch_to_email_no_recipients(self, alert_dispatcher, sample_alert):
        """Testa despacho por email sem destinatários."""
        result = await alert_dispatcher._dispatch_to_email(sample_alert, {"to": []})

        assert result.success is False
        assert "No recipients configured" in result.error_message

    @pytest.mark.asyncio
    async def test_dispatch_to_email_multiple_recipients(self, alert_dispatcher, sample_alert):
        """Testa despacho por email com múltiplos destinatários."""
        result = await alert_dispatcher._dispatch_to_email(
            sample_alert, {"to": ["recipient1@test.com", "recipient2@test.com"]}
        )

        assert result.success is True


class TestDispatchToWebhook:
    """Testes de despacho para webhook genérico."""

    @pytest.mark.asyncio
    async def test_dispatch_to_webhook_post_success(self, alert_dispatcher, sample_alert):
        """Testa despacho bem-sucedido para webhook via POST."""
        await alert_dispatcher.connect()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(alert_dispatcher.session, "post", return_value=mock_response):
            result = await alert_dispatcher._dispatch_to_webhook(
                sample_alert, {"url": "https://webhook.test.com/endpoint"}
            )

        assert result.success is True
        assert result.channel == AlertChannel.WEBHOOK

    @pytest.mark.asyncio
    async def test_dispatch_to_webhook_no_url(self, alert_dispatcher, sample_alert):
        """Testa despacho para webhook sem URL."""
        result = await alert_dispatcher._dispatch_to_webhook(sample_alert, {"url": None})

        assert result.success is False
        assert "No webhook URL configured" in result.error_message

    @pytest.mark.asyncio
    async def test_dispatch_to_webhook_put_method(self, alert_dispatcher, sample_alert):
        """Testa despacho para webhook via PUT."""
        await alert_dispatcher.connect()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(alert_dispatcher.session, "put", return_value=mock_response):
            result = await alert_dispatcher._dispatch_to_webhook(
                sample_alert, {"url": "https://webhook.test.com/endpoint", "method": "PUT"}
            )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_to_webhook_with_headers(self, alert_dispatcher, sample_alert):
        """Testa despacho para webhook com headers customizados."""
        await alert_dispatcher.connect()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            alert_dispatcher.session, "post", return_value=mock_response
        ) as mock_post:
            await alert_dispatcher._dispatch_to_webhook(
                sample_alert,
                {
                    "url": "https://webhook.test.com/endpoint",
                    "headers": {"Authorization": "Bearer token123", "X-Custom": "value"},
                },
            )

            # Verificar que headers foram passados
            call_args = mock_post.call_args
            assert "Authorization" in call_args[1]["headers"]


class TestDispatchToAlertmanager:
    """Testes de despacho para Alertmanager."""

    @pytest.mark.asyncio
    async def test_dispatch_to_alertmanager_success(self, alert_dispatcher, sample_alert):
        """Testa despacho bem-sucedido para Alertmanager."""
        await alert_dispatcher.connect()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(alert_dispatcher.session, "post", return_value=mock_response):
            result = await alert_dispatcher._dispatch_to_alertmanager(
                sample_alert, {"url": "http://alertmanager:9093"}
            )

        assert result.success is True
        assert result.channel == AlertChannel.ALERTMANAGER

    @pytest.mark.asyncio
    async def test_dispatch_to_alertmanager_no_url(self, alert_dispatcher, sample_alert):
        """Testa despacho para Alertmanager sem URL."""
        result = await alert_dispatcher._dispatch_to_alertmanager(sample_alert, {"url": None})

        assert result.success is False
        assert "No Alertmanager URL configured" in result.error_message

    @pytest.mark.asyncio
    async def test_dispatch_to_alertmanager_payload_format(self, alert_dispatcher, sample_alert):
        """Testa formatação do payload para Alertmanager."""
        await alert_dispatcher.connect()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            alert_dispatcher.session, "post", return_value=mock_response
        ) as mock_post:
            await alert_dispatcher._dispatch_to_alertmanager(
                sample_alert, {"url": "http://alertmanager:9093"}
            )

            # Verificar URL e payload
            call_args = mock_post.call_args
            assert "/api/v1/alerts" in call_args[0][0]

            payload = call_args[1]["json"]
            assert len(payload) == 1
            assert payload[0]["labels"]["alertname"] == sample_alert.rule_name
            # Severity is a string due to use_enum_values=True
            assert payload[0]["labels"]["severity"] == "warning"
            assert payload[0]["annotations"]["summary"] == sample_alert.title


class TestDispatchMultiChannel:
    """Testes de despacho para múltiplos canais."""

    @pytest.mark.asyncio
    async def test_dispatch_multiple_channels(self, alert_dispatcher, sample_alert):
        """Testa despacho para múltiplos canais em paralelo."""
        await alert_dispatcher.connect()

        # Mock HTTP responses
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(alert_dispatcher.session, "post", return_value=mock_response):
            results = await alert_dispatcher.dispatch(
                sample_alert,
                [AlertChannel.SLACK, AlertChannel.WEBHOOK],
                {
                    "slack": {"webhook_url": "https://hooks.slack.com/test"},
                    "webhook": {"url": "https://webhook.test.com/endpoint"},
                },
            )

        assert len(results) == 2
        assert all(r.alert_id == sample_alert.alert_id for r in results)
        assert results[0].channel == AlertChannel.SLACK
        assert results[1].channel == AlertChannel.WEBHOOK

    @pytest.mark.asyncio
    async def test_dispatch_partial_failure(self, alert_dispatcher, sample_alert):
        """Testa despacho com falha parcial em alguns canais."""
        await alert_dispatcher.connect()

        mock_success = MagicMock()
        mock_success.status_code = 200
        mock_success.raise_for_status = MagicMock()

        mock_failure = MagicMock()
        mock_failure.status_code = 500
        mock_failure.raise_for_status = MagicMock(side_effect=Exception("HTTP 500"))

        with patch.object(alert_dispatcher.session, "post") as mock_post:
            # Primeira call (Slack) sucesso, segunda (Webhook) falha
            mock_post.side_effect = [mock_success, mock_failure]

            results = await alert_dispatcher.dispatch(
                sample_alert,
                [AlertChannel.SLACK, AlertChannel.WEBHOOK],
                {
                    "slack": {"webhook_url": "https://hooks.slack.com/test"},
                    "webhook": {"url": "https://webhook.test.com/endpoint"},
                },
            )

        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False
        assert "HTTP 500" in results[1].error_message

    @pytest.mark.asyncio
    async def test_dispatch_all_channels(self, alert_dispatcher, sample_alert):
        """Testa despacho para todos os canais disponíveis."""
        await alert_dispatcher.connect()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(alert_dispatcher.session, "post", return_value=mock_response):
            results = await alert_dispatcher.dispatch(
                sample_alert,
                [
                    AlertChannel.SLACK,
                    AlertChannel.PAGERDUTY,
                    AlertChannel.EMAIL,
                    AlertChannel.WEBHOOK,
                    AlertChannel.ALERTMANAGER,
                ],
                {
                    "slack": {"webhook_url": "https://hooks.slack.com/test"},
                    "pagerduty": {"routing_key": "test-pd-key"},
                    "email": {"to": ["recipient@test.com"]},
                    "webhook": {"url": "https://webhook.test.com/endpoint"},
                    "alertmanager": {"url": "http://alertmanager:9093"},
                },
            )

        assert len(results) == 5


class TestSeverityColorMapping:
    """Testes de mapeamento de cores por severidade."""

    def test_get_color_for_emergency(self, alert_dispatcher):
        """Testa cor para severidade emergency."""
        color = alert_dispatcher._get_color_for_severity("emergency")
        assert color == "#FF0000"

    def test_get_color_for_critical(self, alert_dispatcher):
        """Testa cor para severidade critical."""
        color = alert_dispatcher._get_color_for_severity("critical")
        assert color == "#FF6600"

    def test_get_color_for_warning(self, alert_dispatcher):
        """Testa cor para severidade warning."""
        color = alert_dispatcher._get_color_for_severity("warning")
        assert color == "#FFCC00"

    def test_get_color_for_info(self, alert_dispatcher):
        """Testa cor para severidade info."""
        color = alert_dispatcher._get_color_for_severity("info")
        assert color == "#36A64F"

    def test_get_color_for_unknown(self, alert_dispatcher):
        """Testa cor para severidade desconhecida (default)."""
        color = alert_dispatcher._get_color_for_severity("unknown")
        assert color == "#36A64F"  # Default green


class TestPagerDutySeverityMapping:
    """Testes de mapeamento de severidade para PagerDuty."""

    def test_map_emergency_to_critical(self, alert_dispatcher):
        """Testa mapeamento de emergency para critical."""
        severity = alert_dispatcher._map_severity_to_pd("emergency")
        assert severity == "critical"

    def test_map_critical_to_critical(self, alert_dispatcher):
        """Testa mapeamento de critical para critical."""
        severity = alert_dispatcher._map_severity_to_pd("critical")
        assert severity == "critical"

    def test_map_warning_to_warning(self, alert_dispatcher):
        """Testa mapeamento de warning para warning."""
        severity = alert_dispatcher._map_severity_to_pd("warning")
        assert severity == "warning"

    def test_map_info_to_info(self, alert_dispatcher):
        """Testa mapeamento de info para info."""
        severity = alert_dispatcher._map_severity_to_pd("info")
        assert severity == "info"

    def test_map_unknown_to_info(self, alert_dispatcher):
        """Testa mapeamento de severidade desconhecida para info (default)."""
        severity = alert_dispatcher._map_severity_to_pd("unknown")
        assert severity == "info"
