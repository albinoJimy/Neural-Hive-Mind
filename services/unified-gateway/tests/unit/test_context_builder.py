"""
Testes unitários para Context Builder.

Testa R-G4: Context Builder para extrair tenant_id, session_id, user_id de JWT.
Testa INV-7: JWT tokens validated by Unified Gateway must pass user_id, tenant_id to downstream services.
"""

import pytest
from fastapi import HTTPException, Request
from pydantic import ValidationError

from src.middleware.jwt_auth import AuthContext, AuthMethod
from src.models.context import (
    ActorContext,
    ActorType,
    RequestContext,
    RichContext,
    SecurityContext,
    SessionContext,
    TenantContext,
)
from src.services.context_builder import (
    build_request_context,
    build_rich_context,
    ContextBuilder,
    ContextBuilderConfig,
    ContextBuilderError,
    get_context_builder,
)


@pytest.fixture
def context_builder():
    """Retorna instância do Context Builder."""
    return ContextBuilder()


@pytest.fixture
def mock_request():
    """Cria Request mock para testes."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/nhm/request",
        "headers": [
            [b"authorization", b"Bearer test_token"],
            [b"user-agent", b"TestClient/1.0"],
            [b"x-forwarded-for", b"192.168.1.100"],
        ],
        "query_string": b"",
    }
    return Request(scope)


class TestContextBuilderConfig:
    """Testes para ContextBuilderConfig."""

    def test_default_config(self):
        """Configuração padrão deve ter valores esperados."""
        config = ContextBuilderConfig()
        assert config.generate_request_id is True
        assert config.generate_session_id is True
        assert config.extract_client_ip is True
        assert config.extract_user_agent is True
        assert config.default_tenant_id is None
        assert config.session_ttl_hours == 24

    def test_custom_config(self):
        """Configuração customizada deve aceitar valores."""
        config = ContextBuilderConfig(
            generate_request_id=False,
            generate_session_id=False,
            default_tenant_id="default-tenant",
            session_ttl_hours=12,
        )
        assert config.generate_request_id is False
        assert config.generate_session_id is False
        assert config.default_tenant_id == "default-tenant"
        assert config.session_ttl_hours == 12


class TestContextBuilder:
    """Testes para ContextBuilder."""

    def test_initialization(self):
        """Context Builder deve ser inicializado corretamente."""
        builder = ContextBuilder()
        assert builder.config.generate_request_id is True
        assert builder.config.generate_session_id is True

    def test_initialization_with_config(self):
        """Context Builder deve aceitar config customizada."""
        config = ContextBuilderConfig(generate_request_id=False)
        builder = ContextBuilder(config)
        assert builder.config.generate_request_id is False

    def test_generate_request_id(self, context_builder):
        """Deve gerar request_id único no formato correto."""
        request_id = context_builder._generate_request_id()
        assert request_id.startswith("req-")
        assert len(request_id) > 10

    def test_generate_request_id_disabled(self):
        """Se desabilitado, deve retornar 'unknown'."""
        config = ContextBuilderConfig(generate_request_id=False)
        builder = ContextBuilder(config)
        assert builder._generate_request_id() == "unknown"

    def test_extract_input_with_text(self, context_builder):
        """Deve extrair input_text corretamente."""
        input_data = {"input": {"text": "Hello world"}}
        text, files = context_builder._extract_input(input_data)
        assert text == "Hello world"
        assert files == []

    def test_extract_input_with_files(self, context_builder):
        """Deve extrair input_files corretamente."""
        input_data = {"input": {"text": "Test", "files": ["file1.pdf", "file2.txt"]}}
        text, files = context_builder._extract_input(input_data)
        assert text == "Test"
        assert files == ["file1.pdf", "file2.txt"]

    def test_extract_input_empty(self, context_builder):
        """Deve lidar com input vazio."""
        text, files = context_builder._extract_input({})
        assert text is None
        assert files == []

    def test_extract_input_string(self, context_builder):
        """Deve lidar com input como string."""
        input_data = {"input": "Direct text"}
        text, files = context_builder._extract_input(input_data)
        assert text == "Direct text"
        assert files == []

    def test_build_tenant_context_with_id(self, context_builder):
        """Deve construir TenantContext com tenant_id do AuthContext (INV-7)."""
        auth_context = AuthContext(
            authenticated=True, user_id="user-123", tenant_id="tenant-456"
        )
        tenant = context_builder._build_tenant_context(auth_context)
        assert tenant is not None
        assert tenant.tenant_id == "tenant-456"

    def test_build_tenant_context_with_default(self, context_builder):
        """Deve usar tenant_id padrão se não fornecido."""
        config = ContextBuilderConfig(default_tenant_id="default-tenant")
        builder = ContextBuilder(config)
        auth_context = AuthContext(authenticated=False)
        tenant = builder._build_tenant_context(auth_context)
        assert tenant is not None
        assert tenant.tenant_id == "default-tenant"

    def test_build_tenant_context_none(self, context_builder):
        """Deve retornar None sem tenant_id e sem default."""
        auth_context = AuthContext(authenticated=False)
        tenant = context_builder._build_tenant_context(auth_context)
        assert tenant is None

    def test_build_session_context_from_jwt(self, context_builder):
        """Deve extrair session_id do JWT (R-G4)."""
        auth_context = AuthContext(
            authenticated=True,
            user_id="user-123",
            session_id="session-789",
        )
        session = context_builder._build_session_context(auth_context, None)
        assert session is not None
        assert session.session_id == "session-789"
        assert session.actor_id == "user-123"

    def test_build_session_context_generate(self, context_builder):
        """Deve gerar session_id se não presente no JWT."""
        auth_context = AuthContext(authenticated=True, user_id="user-123")
        session = context_builder._build_session_context(auth_context, None)
        assert session is not None
        assert session.session_id.startswith("session-")
        assert session.actor_id == "user-123"

    def test_build_session_context_none_if_disabled(self):
        """Não deve gerar session_id se desabilitado."""
        config = ContextBuilderConfig(generate_session_id=False)
        builder = ContextBuilder(config)
        auth_context = AuthContext(authenticated=True, user_id="user-123")
        session = builder._build_session_context(auth_context, None)
        assert session is None

    def test_build_actor_context_from_jwt(self, context_builder):
        """Deve extrair user_id do JWT (INV-7)."""
        auth_context = AuthContext(
            authenticated=True,
            user_id="user-123",
            permissions=["read", "write"],
        )
        actor = context_builder._build_actor_context(auth_context)
        assert actor is not None
        assert actor.actor_id == "user-123"
        assert actor.actor_type == ActorType.USER
        assert actor.permissions == ["read", "write"]

    def test_build_actor_context_api_key(self, context_builder):
        """Deve detectar ActorType.API_KEY para auth_method api_key."""
        auth_context = AuthContext(
            authenticated=True,
            user_id="api-key-123",
            auth_method=AuthMethod.API_KEY,
        )
        actor = context_builder._build_actor_context(auth_context)
        assert actor.actor_type == ActorType.API_KEY

    def test_build_actor_context_service(self, context_builder):
        """Deve detectar ActorType.SERVICE para user_id iniciando com 'service-'."""
        auth_context = AuthContext(
            authenticated=True,
            user_id="service-nlu",
        )
        actor = context_builder._build_actor_context(auth_context)
        assert actor.actor_type == ActorType.SERVICE

    def test_build_actor_context_none(self, context_builder):
        """Deve retornar None sem user_id."""
        auth_context = AuthContext(authenticated=False)
        actor = context_builder._build_actor_context(auth_context)
        assert actor is None

    def test_extract_client_ip_forwarded(self, context_builder, mock_request):
        """Deve extrair IP de X-Forwarded-For."""
        ip = context_builder._get_client_ip(mock_request)
        assert ip == "192.168.1.100"

    def test_extract_client_ip_real_ip(self, context_builder):
        """Deve extrair IP de X-Real-IP."""
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [[b"x-real-ip", b"10.0.0.1"]],
        }
        request = Request(scope)
        ip = context_builder._get_client_ip(request)
        assert ip == "10.0.0.1"

    def test_extract_client_ip_cf(self, context_builder):
        """Deve extrair IP de CF-Connecting-IP (Cloudflare)."""
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [[b"cf-connecting-ip", b"173.245.0.1"]],
        }
        request = Request(scope)
        ip = context_builder._get_client_ip(request)
        assert ip == "173.245.0.1"

    def test_extract_metadata(self, context_builder, mock_request):
        """Deve extrair metadados da request."""
        metadata = context_builder._extract_metadata(mock_request)
        assert metadata["client_ip"] == "192.168.1.100"
        assert metadata["user_agent"] == "TestClient/1.0"
        assert metadata["method"] == "POST"
        assert metadata["path"] == "/api/v1/nhm/request"

    def test_build_security_context(self, context_builder):
        """Deve construir SecurityContext do AuthContext."""
        auth_context = AuthContext(
            authenticated=True,
            auth_method=AuthMethod.JWT,
            roles=["admin"],
            permissions=["read", "write"],
        )
        security = context_builder._build_security_context(auth_context)
        assert security.authenticated is True
        assert security.auth_method == "jwt"
        assert security.roles == ["admin"]
        assert security.permissions == ["read", "write"]

    @pytest.mark.asyncio
    async def test_build_request_context(
        self, context_builder, mock_request, monkeypatch
    ):
        """Deve construir RequestContext completo."""
        # Mock get_auth_context para retornar AuthContext
        async def mock_get_auth(_):
            return AuthContext(
                authenticated=True,
                user_id="user-123",
                tenant_id="tenant-456",
                session_id="session-789",
                auth_method=AuthMethod.JWT,
            )

        monkeypatch.setattr(
            "src.services.context_builder.get_auth_context", mock_get_auth
        )

        input_data = {"input": {"text": "Test input", "files": ["file1.pdf"]}}

        ctx = await context_builder.build(mock_request, input_data)

        assert isinstance(ctx, RequestContext)
        assert ctx.request_id.startswith("req-")
        assert ctx.input_text == "Test input"
        assert ctx.input_files == ["file1.pdf"]
        assert ctx.tenant is not None
        assert ctx.tenant.tenant_id == "tenant-456"  # INV-7
        assert ctx.session is not None
        assert ctx.session.session_id == "session-789"  # R-G4
        assert ctx.actor is not None
        assert ctx.actor.actor_id == "user-123"  # INV-7
        assert ctx.metadata["client_ip"] == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_build_rich_context(
        self, context_builder, mock_request, monkeypatch
    ):
        """Deve construir RichContext com todas as dimensões."""
        async def mock_get_auth(_):
            return AuthContext(
                authenticated=True,
                user_id="user-123",
                tenant_id="tenant-456",
            )

        monkeypatch.setattr(
            "src.services.context_builder.get_auth_context", mock_get_auth
        )

        rich_ctx = await context_builder.build_rich(mock_request)

        assert isinstance(rich_ctx, RichContext)
        assert rich_ctx.request is not None
        assert rich_ctx.tenant is not None
        assert rich_ctx.session is not None
        assert rich_ctx.actor is not None
        assert rich_ctx.system is not None
        assert rich_ctx.temporal is not None
        assert rich_ctx.security is not None
        assert rich_ctx.security.authenticated is True

    @pytest.mark.asyncio
    async def test_build_unauthenticated(self, context_builder, mock_request, monkeypatch):
        """Deve construir contexto mesmo sem autenticação."""
        async def mock_get_auth(_):
            return AuthContext(authenticated=False)

        monkeypatch.setattr(
            "src.services.context_builder.get_auth_context", mock_get_auth
        )

        ctx = await context_builder.build(mock_request)

        assert ctx.request_id.startswith("req-")
        assert ctx.tenant is None
        # Session é gerado mesmo sem autenticação (generate_session_id=True)
        assert ctx.session is not None
        assert ctx.session.actor_id is None  # Sem user_id
        assert ctx.actor is None


class TestContextBuilderErrors:
    """Testes para erros do Context Builder."""

    def test_context_builder_error_creation(self):
        """ContextBuilderError deve ser criado corretamente."""
        error = ContextBuilderError("Test error", status_code=400)
        assert error.message == "Test error"
        assert error.status_code == 400

    def test_context_builder_error_default_status(self):
        """ContextBuilderError deve ter status 400 por padrão."""
        error = ContextBuilderError("Test error")
        assert error.status_code == 400


class TestDependencyInjection:
    """Testes para dependencies do FastAPI."""

    @pytest.mark.asyncio
    async def test_get_context_builder_singleton(self):
        """get_context_builder deve retornar singleton."""
        builder1 = get_context_builder()
        builder2 = get_context_builder()
        assert builder1 is builder2

    @pytest.mark.asyncio
    async def test_build_request_context_dependency(self, mock_request, monkeypatch):
        """build_request_context deve funcionar como dependency."""
        async def mock_get_auth(_):
            return AuthContext(
                authenticated=True,
                user_id="user-123",
                tenant_id="tenant-456",
            )

        monkeypatch.setattr(
            "src.services.context_builder.get_auth_context", mock_get_auth
        )

        ctx = await build_request_context(mock_request)

        assert isinstance(ctx, RequestContext)
        assert ctx.tenant.tenant_id == "tenant-456"  # INV-7
        assert ctx.actor.actor_id == "user-123"  # INV-7

    @pytest.mark.asyncio
    async def test_build_rich_context_dependency(self, mock_request, monkeypatch):
        """build_rich_context deve funcionar como dependency."""
        async def mock_get_auth(_):
            return AuthContext(authenticated=True, user_id="user-123")

        monkeypatch.setattr(
            "src.services.context_builder.get_auth_context", mock_get_auth
        )

        rich_ctx = await build_rich_context(mock_request)

        assert isinstance(rich_ctx, RichContext)
        assert rich_ctx.request is not None
        assert rich_ctx.security.authenticated is True


class TestInv7Compliance:
    """Testes específicos para INV-7: user_id e tenant_id passados para downstream."""

    def test_inv7_user_id_in_actor_context(self, context_builder):
        """INV-7: user_id deve estar presente no ActorContext."""
        auth_context = AuthContext(authenticated=True, user_id="user-123")
        actor = context_builder._build_actor_context(auth_context)
        assert actor is not None
        assert actor.actor_id == "user-123"

    def test_inv7_tenant_id_in_tenant_context(self, context_builder):
        """INV-7: tenant_id deve estar presente no TenantContext."""
        auth_context = AuthContext(authenticated=True, tenant_id="tenant-456")
        tenant = context_builder._build_tenant_context(auth_context)
        assert tenant is not None
        assert tenant.tenant_id == "tenant-456"

    @pytest.mark.asyncio
    async def test_inv7_full_context(self, context_builder, mock_request, monkeypatch):
        """INV-7: RequestContext completo deve ter user_id e tenant_id."""
        async def mock_get_auth(_):
            return AuthContext(
                authenticated=True,
                user_id="user-inv7",
                tenant_id="tenant-inv7",
                session_id="session-inv7",
            )

        monkeypatch.setattr(
            "src.services.context_builder.get_auth_context", mock_get_auth
        )

        ctx = await context_builder.build(mock_request)

        # Verificar INV-7
        assert ctx.actor is not None, "ActorContext deve existir"
        assert ctx.actor.actor_id == "user-inv7", "user_id deve estar presente"
        assert ctx.tenant is not None, "TenantContext deve existir"
        assert ctx.tenant.tenant_id == "tenant-inv7", "tenant_id deve estar presente"
        assert ctx.session is not None, "SessionContext deve existir (R-G4)"
        assert ctx.session.session_id == "session-inv7", "session_id deve estar presente"


class TestRG4Compliance:
    """Testes específicos para R-G4: session_id extração do JWT."""

    def test_rg4_session_id_from_jwt(self, context_builder):
        """R-G4: session_id deve ser extraído do JWT."""
        auth_context = AuthContext(
            authenticated=True, user_id="user-123", session_id="jwt-session-123"
        )
        session = context_builder._build_session_context(auth_context, None)
        assert session is not None
        assert session.session_id == "jwt-session-123"

    def test_rg4_session_id_generated_if_missing(self, context_builder):
        """R-G4: session_id deve ser gerado se não presente no JWT."""
        auth_context = AuthContext(authenticated=True, user_id="user-123")
        session = context_builder._build_session_context(auth_context, None)
        assert session is not None
        assert session.session_id.startswith("session-")

    def test_rg4_session_id_null_if_no_user(self):
        """R-G4: session_id deve ser None sem user_id quando generate_session_id=False."""
        config = ContextBuilderConfig(generate_session_id=False)
        builder = ContextBuilder(config)
        auth_context = AuthContext(authenticated=False)
        session = builder._build_session_context(auth_context, None)
        assert session is None
