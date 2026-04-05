"""
Testes TDD simplificados para TicketServiceServicer (gRPC).

Foca em comportamentos essenciais sem modelos complexos.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest


# =============================================================================
# Mock Classes
# =============================================================================


class MockProtoRequest:
    """Request mock genérico com atributos padrão."""
    def __init__(self, **kwargs):
        # Atributos padrão para ListTicketsRequest
        self.plan_id = kwargs.get("plan_id", "")
        self.status = kwargs.get("status", "")
        self.offset = kwargs.get("offset", 0)
        self.limit = kwargs.get("limit", 100)

        # Atributos padrão para UpdateTicketStatusRequest
        self.ticket_id = kwargs.get("ticket_id", "")
        self.error_message = kwargs.get("error_message", "")

        # Sobrescrever com valores explícitos
        for key, value in kwargs.items():
            setattr(self, key, value)


class MockProtoTicket:
    """Ticket mockado."""
    def __init__(self, **kwargs):
        self.ticket_id = kwargs.get("ticket_id", "ticket-123")
        self.plan_id = kwargs.get("plan_id", "plan-456")
        self.status = kwargs.get("status", "PENDING")
        self.task_type = kwargs.get("task_type", "query")
        self.priority = kwargs.get("priority", "normal")


class MockProtoResponse:
    """Response mockado genérico."""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_postgres_client():
    """PostgreSQL client mockado."""
    client = AsyncMock()
    return client


@pytest.fixture
def servicer():
    """Instância do TicketServiceServicer."""
    from src.grpc_service.ticket_servicer import TicketServiceServicer

    return TicketServiceServicer()


@pytest.fixture
def mock_grpc_context():
    """Contexto gRPC mockado."""
    context = MagicMock()
    context.set_code = MagicMock()
    context.set_details = MagicMock()
    context.invocation_metadata = {}
    return context


# =============================================================================
# Testes: GetTicket
# =============================================================================


class TestGetTicketSimplified:
    """Testes simplificados do método GetTicket."""

    @pytest.mark.asyncio
    async def test_get_ticket_calls_postgres(
        self, servicer, mock_postgres_client, mock_grpc_context
    ):
        """GetTicket chama postgres client."""
        # Arrange
        mock_orm = MagicMock()
        mock_orm.ticket_id = "ticket-123"
        mock_orm.status = "PENDING"
        mock_orm.to_pydantic = MagicMock(return_value=MockProtoTicket())

        mock_postgres_client.get_ticket_by_id.return_value = mock_orm

        request = MockProtoRequest(ticket_id="ticket-123")

        with patch(
            "src.grpc_service.ticket_servicer.get_postgres_client",
            return_value=mock_postgres_client,
        ):
            # Act
            await servicer.GetTicket(request, mock_grpc_context)

            # Assert
            mock_postgres_client.get_ticket_by_id.assert_called_once_with("ticket-123")

    @pytest.mark.asyncio
    async def test_get_ticket_not_found_sets_grpc_code(
        self, servicer, mock_postgres_client, mock_grpc_context
    ):
        """Ticket não encontrado define código NOT_FOUND."""
        # Arrange
        mock_postgres_client.get_ticket_by_id.return_value = None

        request = MockProtoRequest(ticket_id="nonexistent")

        with patch(
            "src.grpc_service.ticket_servicer.get_postgres_client",
            return_value=mock_postgres_client,
        ):
            # Act
            await servicer.GetTicket(request, mock_grpc_context)

            # Assert
            mock_grpc_context.set_code.assert_called_with(grpc.StatusCode.NOT_FOUND)


# =============================================================================
# Testes: ListTickets
# =============================================================================


class TestListTicketsSimplified:
    """Testes simplificados do método ListTickets."""

    @pytest.mark.asyncio
    async def test_list_tickets_calls_postgres(
        self, servicer, mock_postgres_client, mock_grpc_context
    ):
        """ListTickets chama postgres client."""
        # Arrange
        mock_postgres_client.list_tickets.return_value = []
        mock_postgres_client.count_tickets.return_value = 0

        request = MockProtoRequest(plan_id="plan-456", offset=0, limit=100)

        with patch(
            "src.grpc_service.ticket_servicer.get_postgres_client",
            return_value=mock_postgres_client,
        ):
            # Act
            await servicer.ListTickets(request, mock_grpc_context)

            # Assert
            mock_postgres_client.list_tickets.assert_called_once()
            mock_postgres_client.count_tickets.assert_called_once()


# =============================================================================
# Testes: UpdateTicketStatus
# =============================================================================


class TestUpdateTicketStatusSimplified:
    """Testes simplificados do método UpdateTicketStatus."""

    @pytest.mark.asyncio
    async def test_update_status_calls_postgres(
        self, servicer, mock_postgres_client, mock_grpc_context
    ):
        """UpdateTicketStatus chama postgres client."""
        # Arrange
        from src.models import TicketStatus

        mock_orm = MagicMock()
        mock_orm.ticket_id = "ticket-123"
        mock_orm.status = TicketStatus.RUNNING

        mock_postgres_client.get_ticket_by_id.return_value = mock_orm
        mock_postgres_client.update_ticket_status.return_value = mock_orm

        request = MockProtoRequest(ticket_id="ticket-123", status="RUNNING")

        with patch(
            "src.grpc_service.ticket_servicer.get_postgres_client",
            return_value=mock_postgres_client,
        ):
            # Act
            await servicer.UpdateTicketStatus(request, mock_grpc_context)

            # Assert
            mock_postgres_client.update_ticket_status.assert_called_once()


# =============================================================================
# Testes: GenerateToken
# =============================================================================


class TestGenerateTokenSimplified:
    """Testes simplificados do método GenerateToken."""

    @pytest.mark.asyncio
    async def test_generate_token_requires_ticket(self, servicer, mock_grpc_context):
        """GenerateToken requer que ticket exista."""
        # Arrange
        mock_postgres_client = AsyncMock()
        mock_postgres_client.get_ticket_by_id.return_value = None

        request = MockProtoRequest(ticket_id="ticket-123")

        with patch(
            "src.grpc_service.ticket_servicer.get_postgres_client",
            return_value=mock_postgres_client,
        ), patch("src.grpc_service.ticket_servicer.get_settings"):
            # Act
            await servicer.GenerateToken(request, mock_grpc_context)

            # Assert
            mock_grpc_context.set_code.assert_called_with(grpc.StatusCode.NOT_FOUND)

    @pytest.mark.asyncio
    async def test_generate_token_with_valid_pending_ticket(
        self, servicer, mock_postgres_client, mock_grpc_context
    ):
        """GenerateToken gera token quando ticket existe com status PENDING."""
        # Arrange
        from src.models import (
            TicketStatus,
            ExecutionTicket,
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
        import time

        mock_orm = MagicMock()
        mock_orm.status = TicketStatus.PENDING

        # Criar ExecutionTicket completo e válido
        sla = SLA(deadline=int(time.time() * 1000) + 60000, timeout_ms=30000, max_retries=3)
        qos = QoS(
            delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            consistency=Consistency.EVENTUAL,
            durability=Durability.PERSISTENT,
        )

        mock_ticket = ExecutionTicket(
            ticket_id="ticket-123",
            plan_id="plan-456",
            intent_id="intent-789",
            decision_id="dec-123",
            task_id="task-abc",
            task_type=TaskType.QUERY,
            description="Test ticket",
            status=TicketStatus.PENDING,
            priority=Priority.NORMAL,
            risk_band=RiskBand.low,
            sla=sla,
            qos=qos,
            security_level=SecurityLevel.PUBLIC,
            created_at=int(time.time() * 1000),
            required_capabilities=["read"],
        )

        mock_orm.to_pydantic.return_value = mock_ticket
        mock_postgres_client.get_ticket_by_id.return_value = mock_orm

        request = MockProtoRequest(ticket_id="ticket-123")

        mock_settings = MagicMock()
        mock_settings.jwt_secret_key = "test-secret-key-for-jwt"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_token_expiration_seconds = 3600

        # Mock tracer para evitar AttributeError
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span

        with patch(
            "src.grpc_service.ticket_servicer.get_postgres_client",
            return_value=mock_postgres_client,
        ), patch("src.grpc_service.ticket_servicer.get_settings", return_value=mock_settings), \
        patch("src.grpc_service.ticket_servicer.tracer", mock_tracer), \
        patch("src.grpc_service.ticket_servicer.extract_grpc_context"), \
        patch("src.grpc_service.ticket_servicer.set_baggage"):
            # Act
            response = await servicer.GenerateToken(request, mock_grpc_context)

            # Assert - response deve ter access_token gerado
            assert response.access_token, "Token JWT deve ser gerado"


# =============================================================================
# Testes: Helpers
# =============================================================================


class TestGetEnumValue:
    """Testes da função auxiliar _get_enum_value."""

    def test_get_enum_value_with_enum(self):
        """Enum com atributo value retorna o valor."""
        from src.grpc_service.ticket_servicer import _get_enum_value
        from src.models import TicketStatus

        result = _get_enum_value(TicketStatus.PENDING)
        assert result == "PENDING"

    def test_get_enum_value_with_string(self):
        """String passada diretamente é retornada como string."""
        from src.grpc_service.ticket_servicer import _get_enum_value

        result = _get_enum_value("PENDING")
        assert result == "PENDING"
