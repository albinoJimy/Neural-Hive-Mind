"""Testes unitários para Context Builder."""

import pytest
from pydantic import ValidationError

from src.models.context import (
    ActorContext,
    RequestContext,
    RichContext,
    SessionContext,
    TenantContext,
)


def test_tenant_context_minimal():
    """TenantContext deve ser criado com campos mínimos."""
    context = TenantContext(tenant_id="tenant-123")

    assert context.tenant_id == "tenant-123"
    assert context.name is None
    assert context.settings == {}


def test_tenant_context_full():
    """TenantContext deve aceitar todos os campos."""
    context = TenantContext(
        tenant_id="tenant-123",
        name="Acme Corp",
        settings={"default_flow": "A-F", "rate_limit": 1000},
    )

    assert context.tenant_id == "tenant-123"
    assert context.name == "Acme Corp"
    assert context.settings["default_flow"] == "A-F"


def test_session_context_minimal():
    """SessionContext deve ser criado com campos mínimos."""
    context = SessionContext(session_id="sess-abc")

    assert context.session_id == "sess-abc"
    assert context.actor_id is None
    assert context.created_at is not None


def test_actor_context_minimal():
    """ActorContext deve ser criado com campos mínimos."""
    context = ActorContext(actor_id="user-123", actor_type="user")

    assert context.actor_id == "user-123"
    assert context.actor_type == "user"


def test_actor_context_invalid_type():
    """ActorContext deve rejeitar tipo inválido."""
    with pytest.raises(ValidationError):
        ActorContext(actor_id="user-123", actor_type="invalid")


def test_request_context_minimal():
    """RequestContext deve ser criado com campos mínimos."""
    context = RequestContext(
        request_id="req-001",
        input_text="Criar dashboard de vendas",
    )

    assert context.request_id == "req-001"
    assert context.input_text == "Criar dashboard de vendas"
    assert context.tenant is None
    assert context.session is None
    assert context.actor is None


def test_request_context_full():
    """RequestContext deve aceitar todos os contextos aninhados."""
    tenant = TenantContext(tenant_id="tenant-123", name="Acme")
    session = SessionContext(session_id="sess-abc")
    actor = ActorContext(actor_id="user-123", actor_type="user")

    context = RequestContext(
        request_id="req-001",
        input_text="Teste",
        tenant=tenant,
        session=session,
        actor=actor,
        metadata={"source": "web", "ip": "1.2.3.4"},
    )

    assert context.tenant.tenant_id == "tenant-123"
    assert context.session.session_id == "sess-abc"
    assert context.actor.actor_id == "user-123"
    assert context.metadata["source"] == "web"


def test_rich_context_from_request():
    """RichContext deve ser construído a partir de RequestContext."""
    request_ctx = RequestContext(
        request_id="req-001",
        input_text="Criar dashboard",
        tenant=TenantContext(tenant_id="tenant-123"),
        actor=ActorContext(actor_id="user-123", actor_type="user"),
    )

    rich_ctx = RichContext.from_request(request_ctx)

    assert rich_ctx.request.request_id == "req-001"
    assert rich_ctx.tenant.tenant_id == "tenant-123"
    assert rich_ctx.actor.actor_id == "user-123"
    assert rich_ctx.system is not None
    assert rich_ctx.temporal is not None


def test_rich_context_system_defaults():
    """RichContext deve ter valores padrão para contexto do sistema."""
    request_ctx = RequestContext(request_id="req-001", input_text="Test")
    rich_ctx = RichContext.from_request(request_ctx)

    assert rich_ctx.system.environment is not None
    assert rich_ctx.system.service == "unified-gateway"
    assert rich_ctx.system.version is not None


def test_rich_context_temporal_timestamps():
    """RichContext deve ter timestamps temporais."""
    request_ctx = RequestContext(request_id="req-001", input_text="Test")
    rich_ctx = RichContext.from_request(request_ctx)

    assert rich_ctx.temporal.requested_at is not None
    assert rich_ctx.temporal.expires_at is not None


def test_rich_context_serialization():
    """RichContext deve ser serializável para dict."""
    request_ctx = RequestContext(
        request_id="req-001",
        input_text="Test",
        tenant=TenantContext(tenant_id="tenant-123"),
    )
    rich_ctx = RichContext.from_request(request_ctx)

    data = rich_ctx.model_dump()

    assert "request" in data
    assert "tenant" in data
    assert "system" in data
    assert "temporal" in data
