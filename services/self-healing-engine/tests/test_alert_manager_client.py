"""Testes para o AlertManager Client."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from src.services.alert_manager_client import (
    AlertManagerClient,
    Alert,
    AlertSeverity,
    alert_deadlock_detected,
    alert_memory_leak_detected,
    alert_remediation_started,
    alert_remediation_failed,
)


@pytest.fixture
def mock_httpx_client():
    """Mock do httpx.AsyncClient."""
    client = MagicMock()
    client.post = AsyncMock(return_value=MagicMock(status_code=200))
    return client


@pytest.fixture
def alert_client(mock_httpx_client):
    """AlertManagerClient com HTTP client mockado."""
    client = AlertManagerClient(
        alertmanager_url="http://alertmanager:9093/api/v1/alerts",
        slack_webhook_url="https://hooks.slack.com/test",
        pagerduty_routing_key="test-key",
    )
    client._client = mock_httpx_client
    return client


class TestAlert:
    """Testes para o modelo Alert."""

    def test_alert_creation(self):
        """Testa criação de alerta."""
        alert = Alert(
            alert_name="TestAlert",
            severity=AlertSeverity.WARNING,
            summary="Test summary",
            description="Test description",
            labels={"key": "value"},
            annotations={"key2": "value2"},
        )

        assert alert.alert_name == "TestAlert"
        assert alert.severity == AlertSeverity.WARNING


class TestAlertManagerClient:
    """Testes para o AlertManagerClient."""

    @pytest.mark.asyncio
    async def test_send_alert_all_channels_success(self, alert_client, mock_httpx_client):
        """Testa envio de alerta para todos os canais."""
        mock_httpx_client.post.return_value = MagicMock(status_code=200)

        alert = Alert(
            alert_name="TestAlert",
            severity=AlertSeverity.INFO,
            summary="Test summary",
            description="Test description",
            labels={},
            annotations={},
        )

        result = await alert_client.send_alert(alert)

        assert result is True
        assert mock_httpx_client.post.call_count == 3  # alertmanager + slack + pagerduty

    @pytest.mark.asyncio
    async def test_send_alert_disabled(self, alert_client):
        """Testa que alerta não é enviado quando desabilitado."""
        alert_client.enabled = False

        alert = Alert(
            alert_name="TestAlert",
            severity=AlertSeverity.INFO,
            summary="Test summary",
            description="Test description",
            labels={},
            annotations={},
        )

        result = await alert_client.send_alert(alert)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_alert_only_slack(self, mock_httpx_client):
        """Testa envio apenas para Slack."""
        mock_httpx_client.post.return_value = MagicMock(status_code=200)

        client = AlertManagerClient(
            slack_webhook_url="https://hooks.slack.com/test",
        )
        client._client = mock_httpx_client

        alert = Alert(
            alert_name="TestAlert",
            severity=AlertSeverity.WARNING,
            summary="Test summary",
            description="Test description",
            labels={},
            annotations={},
        )

        result = await client.send_alert(alert)

        assert result is True
        assert mock_httpx_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_send_to_alertmanager_success(self, alert_client, mock_httpx_client):
        """Testa envio bem-sucedido para AlertManager."""
        mock_httpx_client.post.return_value = MagicMock(status_code=200)

        alert = Alert(
            alert_name="TestAlert",
            severity=AlertSeverity.ERROR,
            summary="Test summary",
            description="Test description",
            labels={},
            annotations={},
        )

        result = await alert_client._send_to_alertmanager(alert)

        assert result is True

    @pytest.mark.asyncio
    async def test_send_to_alertmanager_failure(self, alert_client, mock_httpx_client):
        """Testa falha ao enviar para AlertManager."""
        mock_httpx_client.post.return_value = MagicMock(status_code=500)

        alert = Alert(
            alert_name="TestAlert",
            severity=AlertSeverity.ERROR,
            summary="Test summary",
            description="Test description",
            labels={},
            annotations={},
        )

        result = await alert_client._send_to_alertmanager(alert)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_to_slack_success(self, alert_client, mock_httpx_client):
        """Testa envio bem-sucedido para Slack."""
        mock_httpx_client.post.return_value = MagicMock(status_code=200)

        alert = Alert(
            alert_name="TestAlert",
            severity=AlertSeverity.CRITICAL,
            summary="Test summary",
            description="Test description",
            labels={},
            annotations={},
        )

        result = await alert_client._send_to_slack(alert)

        assert result is True

    @pytest.mark.asyncio
    async def test_send_to_pagerduty_success(self, alert_client, mock_httpx_client):
        """Testa envio bem-sucedido para PagerDuty."""
        mock_httpx_client.post.return_value = MagicMock(status_code=202)

        alert = Alert(
            alert_name="TestAlert",
            severity=AlertSeverity.CRITICAL,
            summary="Test summary",
            description="Test description",
            labels={},
            annotations={},
        )

        result = await alert_client._send_to_pagerduty(alert)

        assert result is True

    @pytest.mark.asyncio
    async def test_send_batch_alerts(self, alert_client, mock_httpx_client):
        """Testa envio de múltiplos alertas."""
        mock_httpx_client.post.return_value = MagicMock(status_code=200)

        alerts = [
            Alert(
                alert_name=f"Alert{i}",
                severity=AlertSeverity.INFO,
                summary=f"Summary {i}",
                description=f"Description {i}",
                labels={},
                annotations={},
            )
            for i in range(3)
        ]

        results = await alert_client.send_batch_alerts(alerts)

        # Cada alerta vai para 3 canais = 9 chamadas
        assert results["success"] == 3
        assert results["failed"] == 0
        assert mock_httpx_client.post.call_count == 9

    @pytest.mark.asyncio
    async def test_close_client(self, alert_client):
        """Testa fechamento do cliente."""
        alert_client._client.aclose = AsyncMock()
        await alert_client.close()
        alert_client._client.aclose.assert_called_once()


class TestAlertConvenienceFunctions:
    """Testes para funções de conveniência de alerta."""

    @pytest.mark.asyncio
    async def test_alert_deadlock_detected(self, alert_client, mock_httpx_client):
        """Testa alerta de deadlock detectado."""
        mock_httpx_client.post.return_value = MagicMock(status_code=200)

        await alert_deadlock_detected(
            workflow_id="wf-123",
            stuck_duration_seconds=2400,
            suspected_tickets=["t1", "t2"],
            alert_client=alert_client,
        )

        assert mock_httpx_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_alert_memory_leak_detected(self, alert_client, mock_httpx_client):
        """Testa alerta de memory leak detectado."""
        mock_httpx_client.post.return_value = MagicMock(status_code=200)

        await alert_memory_leak_detected(
            pod_name="worker-1",
            namespace="default",
            usage_percent=95.5,
            duration_above_threshold=300,
            alert_client=alert_client,
        )

        assert mock_httpx_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_alert_remediation_started(self, alert_client, mock_httpx_client):
        """Testa alerta de remediação iniciada."""
        mock_httpx_client.post.return_value = MagicMock(status_code=200)

        await alert_remediation_started(
            remediation_id="rem-123",
            incident_type="deadlock",
            playbook_name="deadlock_recovery",
            alert_client=alert_client,
        )

        assert mock_httpx_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_alert_remediation_failed(self, alert_client, mock_httpx_client):
        """Testa alerta de falha na remediação."""
        mock_httpx_client.post.return_value = MagicMock(status_code=200)

        await alert_remediation_failed(
            remediation_id="rem-123",
            error="Timeout ao executar playbook",
            alert_client=alert_client,
        )

        assert mock_httpx_client.post.call_count == 3
