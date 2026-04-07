"""
Testes unitários para PagerDutyClient.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.clients.pagerduty_client import PagerDutyClient, PagerDutyEvent


@pytest.fixture
def routing_key():
    """Routing key para testes."""
    return "ROUTING_KEY_123"


@pytest.fixture
def pagerduty_client(routing_key):
    """Cliente PagerDuty para testes."""
    return PagerDutyClient(routing_key=routing_key)


class TestPagerDutyClient:
    """Testes para PagerDutyClient."""

    @pytest.mark.asyncio
    async def test_trigger_alert(self, pagerduty_client):
        """Testa trigger de alerta."""
        # Setup
        pagerduty_client.session = AsyncMock()
        response_mock = MagicMock()
        response_mock.status_code = 202  # PagerDuty returns 202
        response_mock.json.return_value = {"dedup_key": "test-dedup-key"}
        response_mock.raise_for_status = MagicMock()
        pagerduty_client.session.post.return_value = response_mock

        # Act
        result = await pagerduty_client.trigger_alert(
            dedup_key="alert-123",
            summary="Test Alert",
            severity="critical",
            source="test-service",
        )

        # Assert
        assert result is True
        pagerduty_client.session.post.assert_called_once()
        call_args = pagerduty_client.session.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["routing_key"] == "ROUTING_KEY_123"
        assert payload["event_action"] == "trigger"
        assert payload["dedup_key"] == "alert-123"

    @pytest.mark.asyncio
    async def test_acknowledge_alert(self, pagerduty_client):
        """Testa acknowledge de alerta."""
        # Setup
        pagerduty_client.session = AsyncMock()
        response_mock = MagicMock()
        response_mock.status_code = 202
        response_mock.raise_for_status = MagicMock()
        pagerduty_client.session.post.return_value = response_mock

        # Act
        result = await pagerduty_client.acknowledge_alert(
            dedup_key="alert-123",
        )

        # Assert
        assert result is True
        call_args = pagerduty_client.session.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["event_action"] == "acknowledge"

    @pytest.mark.asyncio
    async def test_resolve_alert(self, pagerduty_client):
        """Testa resolve de alerta."""
        # Setup
        pagerduty_client.session = AsyncMock()
        response_mock = MagicMock()
        response_mock.status_code = 202
        response_mock.raise_for_status = MagicMock()
        pagerduty_client.session.post.return_value = response_mock

        # Act
        result = await pagerduty_client.resolve_alert(
            dedup_key="alert-123",
        )

        # Assert
        assert result is True
        call_args = pagerduty_client.session.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["event_action"] == "resolve"

    @pytest.mark.asyncio
    async def test_trigger_alert_with_custom_details(self, pagerduty_client):
        """Testa trigger com detalhes customizados."""
        # Setup
        pagerduty_client.session = AsyncMock()
        response_mock = MagicMock()
        response_mock.status_code = 202
        response_mock.raise_for_status = MagicMock()
        pagerduty_client.session.post.return_value = response_mock

        custom_details = {"slo_id": "slo-1", "error_budget": 10.5}

        # Act
        result = await pagerduty_client.trigger_alert(
            dedup_key="alert-456",
            summary="SLA Violation",
            severity="critical",
            source="sla-management",
            custom_details=custom_details,
        )

        # Assert
        assert result is True
        call_args = pagerduty_client.session.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["payload"]["custom_details"] == custom_details

    @pytest.mark.asyncio
    async def test_no_routing_key(self):
        """Testa erro quando não há routing key."""
        # Setup
        client = PagerDutyClient(routing_key=None)

        # Act & Assert
        with pytest.raises(ValueError, match="PagerDuty routing key is required"):
            await client.trigger_alert(
                dedup_key="alert-123",
                summary="Test",
                severity="critical",
                source="test-service",
            )

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self, pagerduty_client):
        """Testa conexão e desconexão."""
        # Act - Connect
        await pagerduty_client.connect()
        assert pagerduty_client.session is not None

        # Act - Disconnect
        await pagerduty_client.disconnect()
        assert pagerduty_client.session is None

    @pytest.mark.asyncio
    async def test_send_sla_alert(self, pagerduty_client):
        """Testa envio de alerta SLA formatado."""
        # Setup
        pagerduty_client.session = AsyncMock()
        response_mock = MagicMock()
        response_mock.status_code = 202
        response_mock.raise_for_status = MagicMock()
        pagerduty_client.session.post.return_value = response_mock

        # Act
        result = await pagerduty_client.send_sla_alert(
            alert_id="sla-123",
            severity="critical",
            title="SLA Violation",
            message="Error budget exceeded",
            service_name="api-gateway",
            slo_id="slo-1",
        )

        # Assert
        assert result is True
        call_args = pagerduty_client.session.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["dedup_key"] == "sla-123"
        assert payload["payload"]["summary"] == "SLA Violation"
        assert payload["payload"]["severity"] == "critical"
        assert payload["payload"]["source"] == "api-gateway"

    def test_severity_mapping_critical(self, pagerduty_client):
        """Testa mapeamento de severidade critical."""
        assert pagerduty_client._map_severity("critical") == "critical"

    def test_severity_mapping_warning(self, pagerduty_client):
        """Testa mapeamento de severidade warning."""
        assert pagerduty_client._map_severity("warning") == "warning"

    def test_severity_mapping_emergency(self, pagerduty_client):
        """Testa mapeamento de severidade emergency."""
        assert pagerduty_client._map_severity("emergency") == "critical"

    def test_severity_mapping_info(self, pagerduty_client):
        """Testa mapeamento de severidade info."""
        assert pagerduty_client._map_severity("info") == "info"


class TestPagerDutyEvent:
    """Testes para modelo PagerDutyEvent."""

    def test_create_event(self):
        """Testa criação de evento PagerDuty."""
        event = PagerDutyEvent(
            routing_key="TEST_KEY",
            event_action="trigger",
            payload={"summary": "Test"},
            dedup_key="test-123",
        )
        assert event.routing_key == "TEST_KEY"
        assert event.event_action == "trigger"
        assert event.dedup_key == "test-123"
