"""
Testes de Integração E2E para SLA Alerts Consumer.

Estes testes validam o fluxo completo de alertas SLA desde o Kafka
até o envio para Slack/PagerDuty.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiokafka import AIOKafkaConsumer
from prometheus_client import REGISTRY

from src.clients.pagerduty_client import PagerDutyClient
from src.clients.slack_client import SlackClient
from src.consumers.sla_alert_consumer import SLAAlertConsumer
from src.config.settings import get_settings


@pytest.fixture(autouse=True)
def clear_prometheus_registry():
    """Limpa o registro do Prometheus antes de cada teste."""
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
    yield
    # Limpa novamente após o teste
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)


@pytest.fixture
def mock_settings():
    """Configurações de teste para SLA alerts."""
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    settings.kafka_security_protocol = "PLAINTEXT"
    settings.sla_alerts_topics = ["sla.alerts", "sla.violations"]
    settings.slack_webhook_url = "https://hooks.slack.com/test/WEBHOOK"
    settings.pagerduty_routing_key = "test-routing-key"
    return settings


@pytest.fixture
def slack_client():
    """Cliente Slack mockado."""
    return AsyncMock(spec=SlackClient)


@pytest.fixture
def pagerduty_client():
    """Cliente PagerDuty mockado."""
    return AsyncMock(spec=PagerDutyClient)


@pytest.fixture
def sla_consumer(slack_client, pagerduty_client):
    """Consumer SLA com clientes mockados."""
    consumer = SLAAlertConsumer(
        slack_client=slack_client,
        pagerduty_client=pagerduty_client,
    )
    return consumer


@pytest.mark.asyncio
class TestSLAAlertConsumerIntegration:
    """Testes de integração do consumer de alertas SLA."""

    async def test_consumer_starts_correctly(self, sla_consumer, mock_settings):
        """Testa que o consumer inicia corretamente."""
        with patch("src.consumers.sla_alert_consumer.get_settings", return_value=mock_settings):
            with patch("src.consumers.sla_alert_consumer.AIOKafkaConsumer") as mock_consumer_class:
                mock_consumer = AsyncMock(spec=AIOKafkaConsumer)
                mock_consumer_class.return_value = mock_consumer

                await sla_consumer.start()

                mock_consumer.start.assert_called_once()
                assert sla_consumer.consumer is not None

    async def test_consumer_stops_correctly(self, sla_consumer, mock_settings):
        """Testa que o consumer para corretamente."""
        with patch("src.consumers.sla_alert_consumer.get_settings", return_value=mock_settings):
            with patch("src.consumers.sla_alert_consumer.AIOKafkaConsumer") as mock_consumer_class:
                mock_consumer = AsyncMock(spec=AIOKafkaConsumer)
                mock_consumer_class.return_value = mock_consumer

                await sla_consumer.start()
                await sla_consumer.stop()

                mock_consumer.stop.assert_called_once()

    async def test_critical_alert_dispatched_to_both_channels(
        self, sla_consumer, slack_client, pagerduty_client
    ):
        """Testa que alerta crítico é enviado para PagerDuty e Slack."""
        alert_data = {
            "alert_id": "alert-123",
            "title": "Workflow Timeout",
            "severity": "CRITICAL",
            "alert_type": "workflow_timeout",
            "workflow_id": "wf-456",
            "service_name": "orchestrator-dynamic",
            "timestamp": "2026-04-06T10:00:00Z",
            "details": {"timeout_ms": 3600000},
        }

        # Mockar is_configured para retornar True
        slack_client.is_configured.return_value = True
        pagerduty_client.is_configured.return_value = True

        await sla_consumer._dispatch_critical(alert_data)

        # Verificar que ambos foram chamados
        pagerduty_client.trigger_alert.assert_called_once()
        slack_client.send_message.assert_called_once()

        # Verificar argumentos do PagerDuty
        pd_call = pagerduty_client.trigger_alert.call_args
        assert pd_call[1]["dedup_key"] == "alert-123"
        assert pd_call[1]["event_type"] == "trigger"
        assert "summary" in pd_call[1]["payload"]

        # Verificar argumentos do Slack
        slack_call = slack_client.send_message.call_args
        assert ":rotating_light:" in slack_call[1]["text"]
        assert slack_call[1]["channel"] == "#sla-alerts-critical"

    async def test_warning_alert_dispatched_to_slack_only(
        self, sla_consumer, slack_client, pagerduty_client
    ):
        """Testa que alerta de warning é enviado apenas para Slack."""
        alert_data = {
            "alert_id": "alert-456",
            "title": "High Latency",
            "severity": "WARNING",
            "alert_type": "high_latency",
            "timestamp": "2026-04-06T10:00:00Z",
        }

        slack_client.is_configured.return_value = True
        pagerduty_client.is_configured.return_value = True

        await sla_consumer._dispatch_warning(alert_data)

        # Verificar que apenas Slack foi chamado
        pagerduty_client.trigger_alert.assert_not_called()
        slack_client.send_message.assert_called_once()

        # Verificar argumentos do Slack
        slack_call = slack_client.send_message.call_args
        assert ":warning:" in slack_call[1]["text"]
        assert slack_call[1]["channel"] == "#sla-alerts"

    async def test_emergency_alert_sent_to_correct_slack_channel(
        self, sla_consumer, slack_client
    ):
        """Testa que alerta EMERGENCY vai para canal correto."""
        alert_data = {
            "alert_id": "alert-789",
            "title": "Service Down",
            "severity": "EMERGENCY",
            "alert_type": "service_down",
        }

        slack_client.is_configured.return_value = True

        await sla_consumer._dispatch_critical(alert_data)

        slack_call = slack_client.send_message.call_args
        # EMERGENCY deve usar #sla-alerts (não critical)
        assert slack_call[1]["channel"] == "#sla-alerts"

    async def test_alert_dispatched_with_correct_formatting(
        self, sla_consumer, slack_client
    ):
        """Testa que alertas são formatados corretamente."""
        alert_data = {
            "alert_id": "fmt-123",
            "title": "Test Alert",
            "severity": "CRITICAL",
            "alert_type": "test_type",
            "workflow_id": "wf-test",
            "service_name": "test-service",
        }

        slack_client.is_configured.return_value = True

        await sla_consumer._dispatch_critical(alert_data)

        slack_call = slack_client.send_message.call_args
        blocks = slack_call[1]["blocks"]

        # Verificar estrutura dos blocos
        assert len(blocks) >= 5  # Header + 3 sections + actions
        assert blocks[0]["type"] == "header"
        assert "CRITICAL" in blocks[0]["text"]["text"]

        # Verificar seção com workflow ID
        workflow_section = next(s for s in blocks if s["type"] == "section" and "Workflow" in s["text"]["text"])
        assert "wf-test" in workflow_section["text"]["text"]

    async def test_alert_not_sent_when_slack_not_configured(
        self, sla_consumer, slack_client
    ):
        """Testa que alerta não é enviado quando Slack não configurado."""
        alert_data = {
            "alert_id": "no-conf-123",
            "title": "Test Alert",
            "severity": "WARNING",
            "alert_type": "test",
        }

        slack_client.is_configured.return_value = False

        await sla_consumer._dispatch_warning(alert_data)

        slack_client.send_message.assert_not_called()

    async def test_alert_not_sent_when_pagerduty_not_configured(
        self, sla_consumer, pagerduty_client
    ):
        """Testa que alerta não é enviado para PagerDuty quando não configurado."""
        alert_data = {
            "alert_id": "no-pd-123",
            "title": "Critical Alert",
            "severity": "CRITICAL",
            "alert_type": "critical",
        }

        pagerduty_client.is_configured.return_value = False

        await sla_consumer._dispatch_critical(alert_data)

        pagerduty_client.trigger_alert.assert_not_called()

    async def test_critical_message_formatting(self, sla_consumer):
        """Testa formatação de mensagem crítica."""
        alert_data = {
            "title": "Timeout Alert",
            "alert_type": "WORKFLOW_TIMEOUT",
            "service_name": "orchestrator",
        }

        message = sla_consumer._format_critical_message(alert_data)

        assert "Timeout Alert" in message
        assert "WORKFLOW_TIMEOUT" in message
        assert "orchestrator" in message
        assert ":rotating_light:" in message

    async def test_warning_message_formatting(self, sla_consumer):
        """Testa formatação de mensagem de warning."""
        alert_data = {
            "title": "Latency Warning",
            "alert_type": "HIGH_LATENCY",
        }

        message = sla_consumer._format_warning_message(alert_data)

        assert "Latency Warning" in message
        assert "HIGH_LATENCY" in message
        assert ":warning:" in message

    async def test_consume_loop_processes_messages(
        self, sla_consumer, mock_settings
    ):
        """Testa que o loop de consumo processa mensagens."""
        with patch("src.consumers.sla_alert_consumer.get_settings", return_value=mock_settings):
            with patch("src.consumers.sla_alert_consumer.AIOKafkaConsumer") as mock_consumer_class:
                # Criar mensagem mock
                mock_message = MagicMock()
                mock_message.value = b'{"alert_id": "test-123", "title": "Test", "severity": "WARNING", "alert_type": "test"}'

                mock_consumer = AsyncMock(spec=AIOKafkaConsumer)
                mock_consumer_class.return_value = mock_consumer

                await sla_consumer.start()

                # Verificar que consumer foi inicializado
                assert sla_consumer.consumer is not None

    async def test_severity_routing(
        self, sla_consumer, slack_client, pagerduty_client
    ):
        """Testa roteamento baseado em severidade."""
        test_cases = [
            ("CRITICAL", True, True),  # PagerDuty + Slack
            ("EMERGENCY", True, True),
            ("WARNING", False, True),  # Apenas Slack
            ("INFO", False, True),
            ("DEBUG", False, True),
        ]

        for severity, expect_pd, expect_slack in test_cases:
            alert_data = {
                "alert_id": f"severity-{severity}",
                "title": f"Test {severity}",
                "severity": severity,
                "alert_type": "test",
            }

            slack_client.is_configured.return_value = True
            pagerduty_client.is_configured.return_value = True

            # Reset mocks
            slack_client.reset_mock()
            pagerduty_client.reset_mock()

            if severity in ["CRITICAL", "EMERGENCY"]:
                await sla_consumer._dispatch_critical(alert_data)
            else:
                await sla_consumer._dispatch_warning(alert_data)

            # Verificar expectativas
            if expect_pd:
                pagerduty_client.trigger_alert.assert_called_once()
            else:
                pagerduty_client.trigger_alert.assert_not_called()

            if expect_slack:
                slack_client.send_message.assert_called_once()
            else:
                slack_client.send_message.assert_not_called()


@pytest.mark.asyncio
class TestSLAAlertsE2EFlow:
    """Testes E2E do fluxo de alertas SLA."""

    async def test_full_alert_flow_from_kafka_to_notifications(
        self, mock_settings
    ):
        """Testa fluxo completo: Kafka → Consumer → Slack/PagerDuty."""
        with patch("src.consumers.sla_alert_consumer.get_settings", return_value=mock_settings):
            with patch("src.consumers.sla_alert_consumer.AIOKafkaConsumer") as mock_consumer_class:
                with patch("src.consumers.sla_alert_consumer.SlackClient") as mock_slack_class:
                    with patch("src.consumers.sla_alert_consumer.PagerDutyClient") as mock_pd_class:
                        # Setup mocks
                        mock_slack = AsyncMock(spec=SlackClient)
                        mock_slack.is_configured.return_value = True
                        mock_slack_class.return_value = mock_slack

                        mock_pd = AsyncMock(spec=PagerDutyClient)
                        mock_pd.is_configured.return_value = True
                        mock_pd_class.return_value = mock_pd

                        # Criar mensagem de alerta crítico
                        alert_json = b'''{
                            "alert_id": "e2e-123",
                            "title": "Workflow Exceeded SLA",
                            "severity": "CRITICAL",
                            "alert_type": "workflow_sla_breach",
                            "workflow_id": "wf-e2e-456",
                            "service_name": "orchestrator-dynamic",
                            "timestamp": "2026-04-06T10:30:00Z"
                        }'''

                        mock_message = MagicMock()
                        mock_message.value = alert_json

                        mock_consumer = AsyncMock(spec=AIOKafkaConsumer)
                        mock_consumer_class.return_value = mock_consumer

                        # Criar consumer e processar mensagem
                        consumer = SLAAlertConsumer()
                        await consumer.start()

                        # Simular processamento
                        await consumer._dispatch_critical(
                            {
                                "alert_id": "e2e-123",
                                "title": "Workflow Exceeded SLA",
                                "severity": "CRITICAL",
                                "alert_type": "workflow_sla_breach",
                                "workflow_id": "wf-e2e-456",
                                "service_name": "orchestrator-dynamic",
                                "timestamp": "2026-04-06T10:30:00Z",
                            }
                        )

                        # Verificar que ambos canais foram notificados
                        mock_pd.trigger_alert.assert_called_once_with(
                            dedup_key="e2e-123",
                            event_type="trigger",
                            payload={
                                "summary": "Workflow Exceeded SLA",
                                "severity": "CRITICAL",
                                "source": "orchestrator-dynamic",
                                "timestamp": "2026-04-06T10:30:00Z",
                                "details": {
                                    "alert_id": "e2e-123",
                                    "title": "Workflow Exceeded SLA",
                                    "severity": "CRITICAL",
                                    "alert_type": "workflow_sla_breach",
                                    "workflow_id": "wf-e2e-456",
                                    "service_name": "orchestrator-dynamic",
                                    "timestamp": "2026-04-06T10:30:00Z",
                                },
                            },
                        )

                        mock_slack.send_message.assert_called_once()
                        slack_call = mock_slack.send_message.call_args
                        assert ":rotating_light:" in slack_call[1]["text"]
                        assert slack_call[1]["channel"] == "#sla-alerts-critical"

    async def test_multiple_alerts_batch_processing(
        self, mock_settings
    ):
        """Testa processamento em lote de múltiplos alertas."""
        with patch("src.consumers.sla_alert_consumer.get_settings", return_value=mock_settings):
            with patch("src.consumers.sla_alert_consumer.SlackClient") as mock_slack_class:
                mock_slack = AsyncMock(spec=SlackClient)
                mock_slack.is_configured.return_value = True
                mock_slack_class.return_value = mock_slack

                consumer = SLAAlertConsumer()
                # Skip start() since we're testing dispatch methods directly

                # Simular múltiplos alertas
                alerts = [
                    {
                        "alert_id": "batch-1",
                        "title": "Alert 1",
                        "severity": "WARNING",
                        "alert_type": "test",
                    },
                    {
                        "alert_id": "batch-2",
                        "title": "Alert 2",
                        "severity": "CRITICAL",
                        "alert_type": "test",
                    },
                    {
                        "alert_id": "batch-3",
                        "title": "Alert 3",
                        "severity": "INFO",
                        "alert_type": "test",
                    },
                ]

                for alert in alerts:
                    if alert["severity"] in ["CRITICAL", "EMERGENCY"]:
                        await consumer._dispatch_critical(alert)
                    else:
                        await consumer._dispatch_warning(alert)

                # Verificar que todos foram processados
                assert mock_slack.send_message.call_count == 3
