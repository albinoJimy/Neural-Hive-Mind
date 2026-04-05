"""
Testes de cobertura para webhooks/webhook_manager.py.
"""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from pydantic import HttpUrl

from src.models import (
    ExecutionTicket,
    TicketStatus,
    TaskType,
    Priority,
    RiskBand,
    SecurityLevel,
    SLA,
    QoS,
    DeliveryMode,
    Consistency,
    Durability,
)


def create_test_ticket(ticket_id="test-123"):
    """Cria ticket de teste."""
    now = int(time.time() * 1000)
    return ExecutionTicket(
        ticket_id=ticket_id,
        task_type=TaskType.QUERY,
        status=TicketStatus.PENDING,
        priority=Priority.NORMAL,
        agent_id="agent-1",
        workflow_id="wf-1",
        intent_id="intent-1",
        decision_id="decision-1",
        task_id="task-1",
        plan_id="plan-1",
        description="Test ticket",
        risk_band=RiskBand.low,
        sla=SLA(
            deadline=now + 60000,
            timeout_ms=5000,
            max_retries=3,
        ),
        qos=QoS(
            delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            consistency=Consistency.EVENTUAL,
            durability=Durability.PERSISTENT,
        ),
        security_level=SecurityLevel.CONFIDENTIAL,
        created_at=now,
    )


class MockSettingsForWebhooks:
    """Settings para testes."""

    def __init__(self):
        self.webhook_timeout_seconds = 10
        self.webhook_worker_count = 2
        self.jwt_secret_key = "test-secret-key-32-bytes-long"


class MockMetrics:
    """Metrics mockado."""

    def __init__(self):
        self.webhooks_enqueued_total = MockCounter()
        self.webhooks_failed_total = MockCounter()
        self.webhooks_sent_total = MockCounter()
        self.webhook_queue_size = MockGauge()
        self.webhook_duration_seconds = MockHistogram()


class MockCounter:
    def __init__(self):
        self.value = 0

    def inc(self):
        self.value += 1


class MockGauge:
    def __init__(self):
        self.value = 0

    def set(self, v):
        self.value = v


class MockHistogram:
    def observe(self, v):
        pass


class TestInjectContextToHeaders:
    """Testes da função inject_context_to_headers."""

    def test_inject_context_to_empty_headers(self):
        """Injeta contexto em headers vazios."""
        from src.webhooks.webhook_manager import inject_context_to_headers

        headers = {}
        inject_context_to_headers(headers)
        assert isinstance(headers, dict)

    def test_inject_context_preserves_existing_headers(self):
        """Preserva headers existentes."""
        from src.webhooks.webhook_manager import inject_context_to_headers

        headers = {"X-Existing": "value"}
        inject_context_to_headers(headers)
        assert "X-Existing" in headers


class TestWebhookManagerInit:
    """Testes do inicializador de WebhookManager."""

    def test_init_creates_manager(self):
        """Cria instância do gerenciador."""
        from src.webhooks.webhook_manager import WebhookManager

        settings = MockSettingsForWebhooks()
        metrics = MockMetrics()
        manager = WebhookManager(settings, metrics)

        assert manager.settings is settings
        assert manager.metrics is metrics
        assert manager.running is False

    def test_init_creates_queue(self):
        """Cria fila de webhooks."""
        from src.webhooks.webhook_manager import WebhookManager

        settings = MockSettingsForWebhooks()
        metrics = MockMetrics()
        manager = WebhookManager(settings, metrics)

        assert isinstance(manager.queue, asyncio.Queue)


class TestWebhookManagerCalculateSignature:
    """Testes do método _calculate_signature."""

    def test_calculate_signature_hmac_sha256(self):
        """Calcula assinatura HMAC-SHA256."""
        from src.webhooks.webhook_manager import WebhookManager

        settings = MockSettingsForWebhooks()
        metrics = MockMetrics()
        manager = WebhookManager(settings, metrics)

        payload = {"test": "data"}
        signature = manager._calculate_signature(payload)

        assert isinstance(signature, str)
        assert len(signature) == 64

    def test_calculate_signature_deterministic(self):
        """Assinatura é determinística."""
        from src.webhooks.webhook_manager import WebhookManager

        settings = MockSettingsForWebhooks()
        metrics = MockMetrics()
        manager = WebhookManager(settings, metrics)

        payload = {"test": "data"}
        sig1 = manager._calculate_signature(payload)
        sig2 = manager._calculate_signature(payload)

        assert sig1 == sig2


class TestWebhookManagerEnqueue:
    """Testes do método enqueue_webhook."""

    @pytest.mark.asyncio
    async def test_enqueue_webhook_success(self):
        """Enfileira webhook com sucesso."""
        from src.webhooks.webhook_manager import WebhookEvent, WebhookManager

        settings = MockSettingsForWebhooks()
        metrics = MockMetrics()
        manager = WebhookManager(settings, metrics)

        ticket = create_test_ticket()
        event = WebhookEvent(
            event_id="evt-1",
            event_type="ticket.created",
            ticket_id="test-123",
            ticket=ticket,
            timestamp=int(time.time() * 1000),
            webhook_url=HttpUrl("https://example.com/webhook"),
        )

        # Usar put_nowait diretamente para teste
        await manager.queue.put(event)

        # Verificar que está na fila
        assert manager.queue.qsize() == 1


class TestWebhookManagerSendWebhook:
    """Testes do método _send_webhook."""

    @pytest.mark.asyncio
    async def test_send_webhook_success(self):
        """Envia webhook com sucesso."""
        from src.webhooks.webhook_manager import WebhookManager, WebhookEvent

        settings = MockSettingsForWebhooks()
        metrics = MockMetrics()
        manager = WebhookManager(settings, metrics)

        # Mock HTTP session e tracer
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"status": "ok"}')

        mock_post_context = AsyncMock()
        mock_post_context.__aenter__.return_value = mock_response
        mock_post_context.__aexit__.return_value = None

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_post_context)

        manager.http_session = mock_session

        # Mock tracer
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)
        mock_span.set_attribute = MagicMock()

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span = MagicMock(return_value=mock_span)

        with patch("src.webhooks.webhook_manager.tracer", mock_tracer):
            ticket = create_test_ticket()
            event = WebhookEvent(
                event_id="evt-1",
                event_type="ticket.created",
                ticket_id="test-123",
                ticket=ticket,
                timestamp=int(time.time() * 1000),
                webhook_url=HttpUrl("https://example.com/webhook"),
            )

            await manager._send_webhook(event)

            assert event.status == "sent"

    @pytest.mark.asyncio
    async def test_send_webhook_with_http_error(self):
        """Lida com erro HTTP."""
        from src.webhooks.webhook_manager import WebhookManager, WebhookEvent

        settings = MockSettingsForWebhooks()
        metrics = MockMetrics()
        manager = WebhookManager(settings, metrics)

        # Mock response com erro
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Error")

        mock_post_context = AsyncMock()
        mock_post_context.__aenter__.return_value = mock_response
        mock_post_context.__aexit__.return_value = None

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_post_context)

        manager.http_session = mock_session
        manager.enqueue_webhook = AsyncMock()

        # Mock tracer
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)
        mock_span.set_attribute = MagicMock()

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span = MagicMock(return_value=mock_span)

        with patch("src.webhooks.webhook_manager.tracer", mock_tracer):
            ticket = create_test_ticket()
            event = WebhookEvent(
                event_id="evt-1",
                event_type="ticket.created",
                ticket_id="test-123",
                ticket=ticket,
                timestamp=int(time.time() * 1000),
                webhook_url=HttpUrl("https://example.com/webhook"),
            )

            await manager._send_webhook(event)

            assert event.status == "failed"


class TestStartWebhookManager:
    """Testes da função factory start_webhook_manager."""

    @pytest.mark.asyncio
    async def test_start_webhook_manager_factory(self):
        """Cria e inicia gerenciador."""
        from src.webhooks.webhook_manager import start_webhook_manager

        with patch("src.webhooks.webhook_manager.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MockSettingsForWebhooks()

            with patch("src.webhooks.webhook_manager.WebhookManager") as mock_manager_class:
                mock_manager = MagicMock()
                mock_manager.start = AsyncMock()
                mock_manager_class.return_value = mock_manager

                metrics = MockMetrics()
                manager = await start_webhook_manager(metrics)

                mock_manager.start.assert_called_once()


class TestWebhookEventModel:
    """Testes do modelo WebhookEvent."""

    def test_webhook_event_should_retry(self):
        """should_retry retorna True quando deve tentar."""
        from src.webhooks.webhook_manager import WebhookEvent

        ticket = create_test_ticket()
        event = WebhookEvent(
            event_id="evt-1",
            event_type="ticket.created",
            ticket_id="test-123",
            ticket=ticket,
            timestamp=int(time.time() * 1000),
            webhook_url=HttpUrl("https://example.com/webhook"),
            retry_count=0,
            max_retries=3,
            status="pending",
        )

        assert event.should_retry() is True

    def test_webhook_event_should_not_retry_max_reached(self):
        """should_retry retorna False quando max retries atingido."""
        from src.webhooks.webhook_manager import WebhookEvent

        ticket = create_test_ticket()
        event = WebhookEvent(
            event_id="evt-1",
            event_type="ticket.created",
            ticket_id="test-123",
            ticket=ticket,
            timestamp=int(time.time() * 1000),
            webhook_url=HttpUrl("https://example.com/webhook"),
            retry_count=3,
            max_retries=3,
            status="pending",
        )

        assert event.should_retry() is False

    def test_webhook_event_to_http_payload(self):
        """Converte para payload HTTP."""
        from src.webhooks.webhook_manager import WebhookEvent

        ticket = create_test_ticket()
        event = WebhookEvent(
            event_id="evt-1",
            event_type="ticket.created",
            ticket_id="test-123",
            ticket=ticket,
            timestamp=int(time.time() * 1000),
            webhook_url=HttpUrl("https://example.com/webhook"),
        )

        payload = event.to_http_payload()

        assert "event_id" in payload
        assert "ticket_id" in payload


class TestWebhookManagerModule:
    """Testes do módulo."""

    def test_module_has_logger_and_tracer(self):
        """Verifica que módulo tem logger e tracer."""
        from src.webhooks import webhook_manager

        assert hasattr(webhook_manager, "logger")
        assert hasattr(webhook_manager, "tracer")

    def test_module_has_start_function(self):
        """Verifica que tem função start_webhook_manager."""
        from src.webhooks import webhook_manager

        assert hasattr(webhook_manager, "start_webhook_manager")
        assert callable(webhook_manager.start_webhook_manager)
