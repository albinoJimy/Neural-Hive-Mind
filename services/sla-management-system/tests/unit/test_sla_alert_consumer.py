"""
Testes unitários para SLAAlertConsumer.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.consumers.sla_alert_consumer import SLAAlertConsumer


@pytest.fixture()
def mock_settings():
    """Configurações mock para testes."""
    settings = MagicMock()
    settings.kafka_bootstrap_servers = ["localhost:9092"]
    settings.sla_alerts_topics = ["sla.alerts", "sla.violations"]
    settings.slack_webhook_url = "https://hooks.slack.com/services/TEST/TEST/TEST"
    settings.pagerduty_routing_key = "TEST_ROUTING_KEY"
    settings.enable_sla_alert_consumer = True
    return settings


@pytest.fixture()
def mock_slack_client():
    """Mock SlackClient."""
    client = AsyncMock()
    client.send_sla_alert = AsyncMock(return_value=True)
    client.send_message = AsyncMock(return_value=True)
    return client


@pytest.fixture()
def mock_pagerduty_client():
    """Mock PagerDutyClient."""
    client = AsyncMock()
    client.send_sla_alert = AsyncMock(return_value=True)
    client.trigger_alert = AsyncMock(return_value=True)
    return client


@pytest.fixture()
def sla_alert_consumer(mock_settings, mock_slack_client, mock_pagerduty_client):
    """Consumer SLA Alert para testes."""
    return SLAAlertConsumer(
        bootstrap_servers=mock_settings.kafka_bootstrap_servers,
        topics=mock_settings.sla_alerts_topics,
        slack_client=mock_slack_client,
        pagerduty_client=mock_pagerduty_client,
    )


class TestSLAAlertConsumer:
    """Testes para SLAAlertConsumer."""

    @pytest.mark.asyncio()
    @patch("src.consumers.sla_alert_consumer.AIOKafkaConsumer")
    async def test_start_creates_consumer(self, mock_kafka_consumer, sla_alert_consumer):
        """Testa que start cria o consumer Kafka."""
        # Setup
        mock_consumer_instance = AsyncMock()
        mock_consumer_instance.start = AsyncMock()
        mock_kafka_consumer.return_value = mock_consumer_instance

        # Act
        await sla_alert_consumer.start()

        # Assert
        assert sla_alert_consumer.consumer is not None
        assert sla_alert_consumer.is_running is True

    @pytest.mark.asyncio()
    @patch("src.consumers.sla_alert_consumer.AIOKafkaConsumer")
    async def test_stop_stops_consumer(self, mock_kafka_consumer, sla_alert_consumer):
        """Testa que stop para o consumer."""
        # Setup
        mock_consumer_instance = AsyncMock()
        mock_consumer_instance.start = AsyncMock()
        mock_consumer_instance.stop = AsyncMock()
        mock_kafka_consumer.return_value = mock_consumer_instance

        await sla_alert_consumer.start()

        # Act
        await sla_alert_consumer.stop()

        # Assert
        assert sla_alert_consumer.is_running is False

    @pytest.mark.asyncio()
    async def test_dispatch_critical_alert(self, sla_alert_consumer):
        """Testa despacho de alerta crítico para Slack + PagerDuty."""
        # Setup
        alert_data = {
            "alert_id": "alert-123",
            "severity": "critical",
            "title": "SLA Violation",
            "message": "Error budget exceeded",
            "service_name": "api-gateway",
            "slo_id": "slo-1",
            "error_budget_remaining": 10.0,
        }

        # Act
        await sla_alert_consumer._dispatch_critical(alert_data)

        # Assert
        sla_alert_consumer.slack_client.send_sla_alert.assert_called_once()
        sla_alert_consumer.pagerduty_client.send_sla_alert.assert_called_once()

    @pytest.mark.asyncio()
    async def test_dispatch_emergency_alert(self, sla_alert_consumer):
        """Testa despacho de alerta emergency para Slack + PagerDuty."""
        # Setup
        alert_data = {
            "alert_id": "alert-456",
            "severity": "emergency",
            "title": "Complete Service Outage",
            "message": "All systems down",
            "service_name": "api-gateway",
        }

        # Act
        await sla_alert_consumer._dispatch_critical(alert_data)

        # Assert
        sla_alert_consumer.slack_client.send_sla_alert.assert_called_once()
        sla_alert_consumer.pagerduty_client.send_sla_alert.assert_called_once()

    @pytest.mark.asyncio()
    async def test_dispatch_warning_alert(self, sla_alert_consumer):
        """Testa despacho de alerta warning apenas para Slack."""
        # Setup
        alert_data = {
            "alert_id": "alert-789",
            "severity": "warning",
            "title": "High Error Rate",
            "message": "Error rate above threshold",
            "service_name": "api-gateway",
        }

        # Act
        await sla_alert_consumer._dispatch_warning(alert_data)

        # Assert
        sla_alert_consumer.slack_client.send_sla_alert.assert_called_once()
        sla_alert_consumer.pagerduty_client.send_sla_alert.assert_not_called()

    @pytest.mark.asyncio()
    async def test_dispatch_info_alert(self, sla_alert_consumer):
        """Testa despacho de alerta info apenas para Slack."""
        # Setup
        alert_data = {
            "alert_id": "alert-999",
            "severity": "info",
            "title": "SLA Update",
            "message": "SLO definition updated",
            "service_name": "sla-management",
        }

        # Act
        await sla_alert_consumer._dispatch_warning(alert_data)

        # Assert
        sla_alert_consumer.slack_client.send_sla_alert.assert_called_once()

    @pytest.mark.asyncio()
    async def test_process_alert_message_critical(self, sla_alert_consumer):
        """Testa processamento de mensagem de alerta crítico."""
        # Setup
        message = MagicMock()
        message.value = json.dumps(
            {
                "alert_id": "alert-001",
                "severity": "critical",
                "title": "Test Alert",
                "message": "Test message",
                "service_name": "test-service",
            }
        ).encode()

        # Act
        await sla_alert_consumer._process_message(message)

        # Assert
        sla_alert_consumer.slack_client.send_sla_alert.assert_called_once()
        sla_alert_consumer.pagerduty_client.send_sla_alert.assert_called_once()

    @pytest.mark.asyncio()
    async def test_process_alert_message_warning(self, sla_alert_consumer):
        """Testa processamento de mensagem de alerta warning."""
        # Setup
        message = MagicMock()
        message.value = json.dumps(
            {
                "alert_id": "alert-002",
                "severity": "warning",
                "title": "Test Warning",
                "message": "Test warning message",
                "service_name": "test-service",
            }
        ).encode()

        # Act
        await sla_alert_consumer._process_message(message)

        # Assert
        sla_alert_consumer.slack_client.send_sla_alert.assert_called_once()
        sla_alert_consumer.pagerduty_client.send_sla_alert.assert_not_called()

    @pytest.mark.asyncio()
    async def test_process_invalid_json_message(self, sla_alert_consumer, caplog):
        """Testa processamento de mensagem JSON inválido."""
        # Setup
        message = MagicMock()
        message.value = b"invalid json"

        # Act
        await sla_alert_consumer._process_message(message)

        # Assert - não deve levantar exceção
        sla_alert_consumer.slack_client.send_sla_alert.assert_not_called()

    def test_is_critical_severity(self, sla_alert_consumer):
        """Testa identificação de severidades críticas."""
        assert sla_alert_consumer._is_critical_severity("critical") is True
        assert sla_alert_consumer._is_critical_severity("emergency") is True
        assert sla_alert_consumer._is_critical_severity("warning") is False
        assert sla_alert_consumer._is_critical_severity("info") is False

    def test_get_emoji_for_severity(self, sla_alert_consumer):
        """Testa obtenção de emoji para severidade."""
        assert sla_alert_consumer._get_emoji("critical") in [":warning:", ":rotating_light:"]
        assert sla_alert_consumer._get_emoji("warning") in [":large_orange_diamond:", ":warning:"]
        assert sla_alert_consumer._get_emoji("info") == ":information_source:"


class TestSLAAlertConsumerFormatting:
    """Testes para formatação de mensagens Slack."""

    @pytest.fixture()
    def consumer(self, mock_settings, mock_slack_client, mock_pagerduty_client):
        """Consumer para testes de formatação."""
        return SLAAlertConsumer(
            bootstrap_servers=mock_settings.kafka_bootstrap_servers,
            topics=mock_settings.sla_alerts_topics,
            slack_client=mock_slack_client,
            pagerduty_client=mock_pagerduty_client,
        )

    def test_format_slack_blocks_critical(self, consumer):
        """Testa formatação de blocks Slack para alerta crítico."""
        alert_data = {
            "alert_id": "alert-123",
            "severity": "critical",
            "title": "SLA Violation",
            "message": "Error budget exceeded",
            "service_name": "api-gateway",
            "slo_id": "slo-1",
            "error_budget_remaining": 10.0,
        }

        blocks = consumer._format_slack_blocks(alert_data)

        assert isinstance(blocks, list)
        assert len(blocks) > 0
        assert any("header" in str(b) for b in blocks)
        assert any("section" in str(b) for b in blocks)

    def test_format_slack_blocks_warning(self, consumer):
        """Testa formatação de blocks Slack para alerta warning."""
        alert_data = {
            "alert_id": "alert-456",
            "severity": "warning",
            "title": "High Error Rate",
            "message": "Error rate above threshold",
            "service_name": "api-gateway",
        }

        blocks = consumer._format_slack_blocks(alert_data)

        assert isinstance(blocks, list)
        assert len(blocks) > 0
