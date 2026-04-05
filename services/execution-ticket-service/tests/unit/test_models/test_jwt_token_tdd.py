"""
Testes TDD para JWT Token functions.

Foca em testes funcionais de geração/validação de tokens.
"""

import time
from unittest.mock import patch

import pytest


# =============================================================================
# Testes: generate_token
# =============================================================================


class TestGenerateToken:
    """Testes da função generate_token."""

    @pytest.mark.asyncio
    async def test_generate_token_returns_jwt_token(self):
        """generate_token retorna JWTToken."""
        # Arrange
        from src.models.jwt_token import generate_token
        from src.models import ExecutionTicket, TaskType, TicketStatus, Priority, RiskBand, SecurityLevel, SLA, QoS, DeliveryMode, Consistency, Durability

        sla = SLA(deadline=int(time.time() * 1000) + 60000, timeout_ms=30000, max_retries=3)
        qos = QoS(
            delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            consistency=Consistency.EVENTUAL,
            durability=Durability.PERSISTENT,
        )

        ticket = ExecutionTicket(
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

        # Act
        result = generate_token(
            ticket,
            secret_key="test-secret-key-32-bytes-long",
            algorithm="HS256",
            expiration_seconds=3600,
        )

        # Assert
        assert result.access_token is not None
        assert result.token_type == "Bearer"
        assert result.expires_in == 3600
        assert result.ticket_id == "ticket-123"
        assert isinstance(result.scopes, list)

    @pytest.mark.asyncio
    async def test_generate_token_includes_expected_scopes(self):
        """generate_token inclui scopes esperados."""
        # Arrange
        from src.models.jwt_token import generate_token
        from src.models import ExecutionTicket, TaskType, TicketStatus, Priority, RiskBand, SecurityLevel, SLA, QoS, DeliveryMode, Consistency, Durability

        sla = SLA(deadline=int(time.time() * 1000) + 60000, timeout_ms=30000, max_retries=3)
        qos = QoS(
            delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            consistency=Consistency.EVENTUAL,
            durability=Durability.PERSISTENT,
        )

        ticket = ExecutionTicket(
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

        # Act
        result = generate_token(
            ticket,
            secret_key="test-secret-key-32-bytes-long",
            algorithm="HS256",
            expiration_seconds=3600,
        )

        # Assert
        assert "ticket:read" in result.scopes
        assert "ticket:update" in result.scopes
        assert "task:query" in result.scopes

    @pytest.mark.asyncio
    async def test_generate_token_with_confidential_security_includes_elevated_scope(self):
        """generate_token com security_level CONFIDENTIAL inclui scope elevado."""
        # Arrange
        from src.models.jwt_token import generate_token
        from src.models import ExecutionTicket, TaskType, TicketStatus, Priority, RiskBand, SecurityLevel, SLA, QoS, DeliveryMode, Consistency, Durability

        sla = SLA(deadline=int(time.time() * 1000) + 60000, timeout_ms=30000, max_retries=3)
        qos = QoS(
            delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            consistency=Consistency.EVENTUAL,
            durability=Durability.PERSISTENT,
        )

        ticket = ExecutionTicket(
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
            security_level=SecurityLevel.CONFIDENTIAL,
            created_at=int(time.time() * 1000),
            required_capabilities=["read"],
        )

        # Act
        result = generate_token(
            ticket,
            secret_key="test-secret-key-32-bytes-long",
            algorithm="HS256",
            expiration_seconds=3600,
        )

        # Assert
        assert "security:elevated" in result.scopes


# =============================================================================
# Testes: decode_token
# =============================================================================


class TestDecodeToken:
    """Testes da função decode_token."""

    @pytest.mark.asyncio
    async def test_decode_token_returns_payload(self):
        """decode_token retorna payload do token."""
        # Arrange
        from src.models.jwt_token import generate_token, decode_token
        from src.models import ExecutionTicket, TaskType, TicketStatus, Priority, RiskBand, SecurityLevel, SLA, QoS, DeliveryMode, Consistency, Durability

        sla = SLA(deadline=int(time.time() * 1000) + 60000, timeout_ms=30000, max_retries=3)
        qos = QoS(
            delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            consistency=Consistency.EVENTUAL,
            durability=Durability.PERSISTENT,
        )

        ticket = ExecutionTicket(
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

        secret = "test-secret-key-32-bytes-long"
        token = generate_token(ticket, secret, "HS256", 3600)

        # Act
        payload = decode_token(token.access_token, secret, "HS256")

        # Assert
        assert payload.ticket_id == "ticket-123"
        assert payload.plan_id == "plan-456"
        assert payload.iss == "neural-hive-mind"
        assert payload.aud == "worker-agents"

    @pytest.mark.asyncio
    async def test_decode_token_raises_on_invalid_signature(self):
        """decode_token raise em token com assinatura inválida."""
        # Arrange
        from src.models.jwt_token import decode_token
        import jwt

        invalid_token = jwt.encode({"test": "data"}, "wrong-secret", algorithm="HS256")

        # Act & Assert
        with pytest.raises(Exception):
            decode_token(invalid_token, "correct-secret", "HS256")


# =============================================================================
# Testes: validate_token
# =============================================================================


class TestValidateToken:
    """Testes da função validate_token."""

    @pytest.mark.asyncio
    async def test_validate_token_returns_true_for_valid_token(self):
        """validate_token retorna True para token válido."""
        # Arrange
        from src.models.jwt_token import generate_token, validate_token
        from src.models import ExecutionTicket, TaskType, TicketStatus, Priority, RiskBand, SecurityLevel, SLA, QoS, DeliveryMode, Consistency, Durability

        sla = SLA(deadline=int(time.time() * 1000) + 60000, timeout_ms=30000, max_retries=3)
        qos = QoS(
            delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            consistency=Consistency.EVENTUAL,
            durability=Durability.PERSISTENT,
        )

        ticket = ExecutionTicket(
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

        secret = "test-secret-key-32-bytes-long"
        token = generate_token(ticket, secret, "HS256", 3600)

        # Act
        result = validate_token(token.access_token, "ticket-123", secret, "HS256")

        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_token_returns_false_for_wrong_ticket_id(self):
        """validate_token retorna False para ticket_id diferente."""
        # Arrange
        from src.models.jwt_token import generate_token, validate_token
        from src.models import ExecutionTicket, TaskType, TicketStatus, Priority, RiskBand, SecurityLevel, SLA, QoS, DeliveryMode, Consistency, Durability

        sla = SLA(deadline=int(time.time() * 1000) + 60000, timeout_ms=30000, max_retries=3)
        qos = QoS(
            delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            consistency=Consistency.EVENTUAL,
            durability=Durability.PERSISTENT,
        )

        ticket = ExecutionTicket(
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

        secret = "test-secret-key-32-bytes-long"
        token = generate_token(ticket, secret, "HS256", 3600)

        # Act
        result = validate_token(token.access_token, "different-ticket-id", secret, "HS256")

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_token_returns_false_for_invalid_token(self):
        """validate_token retorna False para token inválido."""
        # Arrange
        from src.models.jwt_token import validate_token

        # Act
        result = validate_token("invalid-token", "ticket-123", "secret", "HS256")

        # Assert
        assert result is False


# =============================================================================
# Testes: JWTTokenPayload
# =============================================================================


class TestJWTTokenPayload:
    """Testes do modelo JWTTokenPayload."""

    def test_jwt_token_payload_requires_fields(self):
        """JWTTokenPayload requer campos obrigatórios."""
        # Arrange
        from src.models.jwt_token import JWTTokenPayload
        from pydantic import ValidationError

        # Act & Assert
        with pytest.raises(ValidationError):
            JWTTokenPayload()

    def test_jwt_token_payload_accepts_valid_data(self):
        """JWTTokenPayload aceita dados válidos."""
        # Arrange
        from src.models.jwt_token import JWTTokenPayload
        import time

        current_time = int(time.time())

        # Act
        payload = JWTTokenPayload(
            sub="ticket-123",
            iss="neural-hive-mind",
            aud="worker-agents",
            exp=current_time + 3600,
            iat=current_time,
            jti="unique-id",
            ticket_id="ticket-123",
            plan_id="plan-456",
            intent_id="intent-789",
            task_type="query",
            security_level="PUBLIC",
            required_capabilities=["read"],
            scopes=["ticket:read"],
        )

        # Assert
        assert payload.ticket_id == "ticket-123"
        assert payload.iss == "neural-hive-mind"


# =============================================================================
# Testes: JWTToken
# =============================================================================


class TestJWTTokenModel:
    """Testes do modelo JWTToken."""

    def test_jwt_token_requires_access_token(self):
        """JWTToken requer access_token."""
        # Arrange
        from src.models.jwt_token import JWTToken
        from pydantic import ValidationError

        # Act & Assert
        with pytest.raises(ValidationError):
            JWTToken(
                token_type="Bearer",
                expires_in=3600,
                expires_at=1234567890,
                ticket_id="ticket-123",
                scopes=["ticket:read"],
            )

    def test_jwt_token_accepts_valid_data(self):
        """JWTToken aceita dados válidos."""
        # Arrange
        from src.models.jwt_token import JWTToken

        # Act
        token = JWTToken(
            access_token="encoded-jwt-token",
            token_type="Bearer",
            expires_in=3600,
            expires_at=1234567890,
            ticket_id="ticket-123",
            scopes=["ticket:read"],
        )

        # Assert
        assert token.access_token == "encoded-jwt-token"
        assert token.ticket_id == "ticket-123"
