"""
Testes para SecurityHeadersMiddleware.

Valida que todos os headers de segurança são adicionados corretamente
às respostas HTTP.
"""

from unittest.mock import AsyncMock, Mock

import pytest
from starlette.applications import Starlette
from starlette.responses import Response


# Import AFTER setting PYTHONPATH
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from neural_hive_security.security_headers import (
    SecurityHeadersMiddleware,
    SecurityHeadersMiddlewareConfig,
)


@pytest.fixture
def mock_app():
    """Aplicação FastAPI/Starlette mockada."""
    app = Starlette()

    @app.route("/")
    async def home(request):
        return Response(content="OK", status_code=200)

    @app.route("/api/test")
    async def test_endpoint(request):
        return Response(content='{"test": "data"}', status_code=200)

    return app


@pytest.fixture
def security_middleware(mock_app):
    """Middleware de headers de segurança."""
    return SecurityHeadersMiddleware(mock_app)


class TestSecurityHeadersMiddleware:
    """Testes do SecurityHeadersMiddleware."""

    @pytest.mark.asyncio
    async def test_adds_x_content_type_options(self, security_middleware):
        """Testa que X-Content-Type-Options é adicionado."""
        request = Mock()
        request.scope = {"type": "http"}
        call_next = AsyncMock(return_value=Response(content="OK"))

        response = await security_middleware.dispatch(request, call_next)

        assert response.headers["X-Content-Type-Options"] == "nosniff"

    @pytest.mark.asyncio
    async def test_adds_x_frame_options(self, security_middleware):
        """Testa que X-Frame-Options é adicionado."""
        request = Mock()
        request.scope = {"type": "http"}
        call_next = AsyncMock(return_value=Response(content="OK"))

        response = await security_middleware.dispatch(request, call_next)

        assert response.headers["X-Frame-Options"] == "DENY"

    @pytest.mark.asyncio
    async def test_adds_content_security_policy(self, security_middleware):
        """Testa que Content-Security-Policy é adicionado."""
        request = Mock()
        request.scope = {"type": "http"}
        call_next = AsyncMock(return_value=Response(content="OK"))

        response = await security_middleware.dispatch(request, call_next)

        csp = response.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "style-src 'self'" in csp
        assert "object-src 'none'" in csp
        assert "upgrade-insecure-requests" in csp

    @pytest.mark.asyncio
    async def test_adds_strict_transport_security(self, security_middleware):
        """Testa que Strict-Transport-Security é adicionado."""
        request = Mock()
        request.scope = {"type": "http"}
        call_next = AsyncMock(return_value=Response(content="OK"))

        response = await security_middleware.dispatch(request, call_next)

        hsts = response.headers["Strict-Transport-Security"]
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts
        assert "preload" not in hsts

    @pytest.mark.asyncio
    async def test_hsts_with_preload(self, mock_app):
        """Testa HSTS com flag preload."""
        middleware = SecurityHeadersMiddleware(mock_app, hsts_preload=True)
        request = Mock()
        request.scope = {"type": "http"}
        call_next = AsyncMock(return_value=Response(content="OK"))

        response = await middleware.dispatch(request, call_next)

        hsts = response.headers["Strict-Transport-Security"]
        assert "preload" in hsts

    @pytest.mark.asyncio
    async def test_adds_x_xss_protection(self, security_middleware):
        """Testa que X-XSS-Protection é adicionado."""
        request = Mock()
        request.scope = {"type": "http"}
        call_next = AsyncMock(return_value=Response(content="OK"))

        response = await security_middleware.dispatch(request, call_next)

        assert response.headers["X-XSS-Protection"] == "1; mode=block"

    @pytest.mark.asyncio
    async def test_adds_referrer_policy(self, security_middleware):
        """Testa que Referrer-Policy é adicionado."""
        request = Mock()
        request.scope = {"type": "http"}
        call_next = AsyncMock(return_value=Response(content="OK"))

        response = await security_middleware.dispatch(request, call_next)

        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_adds_permissions_policy(self, security_middleware):
        """Testa que Permissions-Policy é adicionado."""
        request = Mock()
        request.scope = {"type": "http"}
        call_next = AsyncMock(return_value=Response(content="OK"))

        response = await security_middleware.dispatch(request, call_next)

        permissions = response.headers["Permissions-Policy"]
        assert "geolocation=()" in permissions
        assert "microphone=()" in permissions
        assert "camera=()" in permissions

    @pytest.mark.asyncio
    async def test_adds_cross_origin_opener_policy(self, security_middleware):
        """Testa que Cross-Origin-Opener-Policy é adicionado."""
        request = Mock()
        request.scope = {"type": "http"}
        call_next = AsyncMock(return_value=Response(content="OK"))

        response = await security_middleware.dispatch(request, call_next)

        assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"

    @pytest.mark.asyncio
    async def test_adds_cross_origin_resource_policy(self, security_middleware):
        """Testa que Cross-Origin-Resource-Policy é adicionado."""
        request = Mock()
        request.scope = {"type": "http"}
        call_next = AsyncMock(return_value=Response(content="OK"))

        response = await security_middleware.dispatch(request, call_next)

        assert response.headers["Cross-Origin-Resource-Policy"] == "same-site"

    @pytest.mark.asyncio
    async def test_adds_x_permitted_cross_domain_policies(self, security_middleware):
        """Testa que X-Permitted-Cross-Domain-Policies é adicionado."""
        request = Mock()
        request.scope = {"type": "http"}
        call_next = AsyncMock(return_value=Response(content="OK"))

        response = await security_middleware.dispatch(request, call_next)

        assert response.headers["X-Permitted-Cross-Domain-Policies"] == "none"

    @pytest.mark.asyncio
    async def test_csp_without_unsafe_inline(self, mock_app):
        """Testa CSP sem unsafe-inline (modo estrito)."""
        middleware = SecurityHeadersMiddleware(mock_app, csp_include_unsafe_inline=False)
        request = Mock()
        request.scope = {"type": "http"}
        call_next = AsyncMock(return_value=Response(content="OK"))

        response = await middleware.dispatch(request, call_next)

        csp = response.headers["Content-Security-Policy"]
        assert "unsafe-inline" not in csp
        assert "script-src 'self'" in csp

    @pytest.mark.asyncio
    async def test_csp_with_unsafe_inline_default(self, security_middleware):
        """Testa CSP com unsafe-inline (padrão para compatibilidade)."""
        request = Mock()
        request.scope = {"type": "http"}
        call_next = AsyncMock(return_value=Response(content="OK"))

        response = await security_middleware.dispatch(request, call_next)

        csp = response.headers["Content-Security-Policy"]
        assert "unsafe-inline" in csp

    @pytest.mark.asyncio
    async def test_hsts_without_subdomains(self, mock_app):
        """Testa HSTS sem incluir subdomínios."""
        middleware = SecurityHeadersMiddleware(mock_app, hsts_include_subdomains=False)
        request = Mock()
        request.scope = {"type": "http"}
        call_next = AsyncMock(return_value=Response(content="OK"))

        response = await middleware.dispatch(request, call_next)

        hsts = response.headers["Strict-Transport-Security"]
        assert "includeSubDomains" not in hsts
        assert "max-age=31536000" in hsts

    @pytest.mark.asyncio
    async def test_all_security_headers_present(self, security_middleware):
        """Testa que todos os headers de segurança estão presentes."""
        request = Mock()
        request.scope = {"type": "http"}
        call_next = AsyncMock(return_value=Response(content="OK"))

        response = await security_middleware.dispatch(request, call_next)

        required_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "Content-Security-Policy",
            "Strict-Transport-Security",
            "X-XSS-Protection",
            "Referrer-Policy",
            "Permissions-Policy",
            "X-Permitted-Cross-Domain-Policies",
            "Cross-Origin-Opener-Policy",
            "Cross-Origin-Resource-Policy",
        ]

        for header in required_headers:
            assert header in response.headers, f"Missing header: {header}"


class TestSecurityHeadersMiddlewareConfig:
    """Testes da SecurityHeadersMiddlewareConfig."""

    def test_default_config(self):
        """Testa configuração padrão."""
        config = SecurityHeadersMiddlewareConfig()

        assert config.csp_include_unsafe_inline is True
        assert config.hsts_include_subdomains is True
        assert config.hsts_preload is False
        assert config.custom_headers == {}

    def test_custom_config(self):
        """Testa configuração customizada."""
        config = SecurityHeadersMiddlewareConfig(
            csp_include_unsafe_inline=False,
            hsts_include_subdomains=False,
            hsts_preload=True,
            custom_headers={"X-Custom-Header": "custom-value"},
        )

        assert config.csp_include_unsafe_inline is False
        assert config.hsts_include_subdomains is False
        assert config.hsts_preload is True
        assert config.custom_headers["X-Custom-Header"] == "custom-value"

    def test_as_kwargs(self):
        """Testa método as_kwargs."""
        config = SecurityHeadersMiddlewareConfig(
            csp_include_unsafe_inline=False,
            hsts_preload=True,
        )

        kwargs = config.as_kwargs()

        assert kwargs == {
            "csp_include_unsafe_inline": False,
            "hsts_include_subdomains": True,
            "hsts_preload": True,
        }
