"""
Testes para SecurityHeadersMiddleware.

Autor: Neural Hive Mind
Criado: 2026-04-19 (SEC-001)
"""

import pytest
from fastapi import FastAPI, Response
from httpx import ASGITransport, AsyncClient

from neural_hive_security.security_headers import (
    SecurityHeadersConfig,
    SecurityHeadersMiddleware,
    add_security_headers,
)


class TestSecurityHeadersConfig:
    """Testes para configuração de headers de segurança."""

    def test_default_config(self):
        """Testa configuração padrão."""
        config = SecurityHeadersConfig()
        headers = config.to_dict()

        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["X-XSS-Protection"] == "1; mode=block"
        assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_csp_header_contains_defaults(self):
        """Testa CSP contém diretivas padrão."""
        config = SecurityHeadersConfig()
        headers = config.to_dict()

        csp = headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "connect-src 'self'" in csp

    def test_hsts_header(self):
        """Testa HSTS com configuração correta."""
        config = SecurityHeadersConfig()
        headers = config.to_dict()

        hsts = headers["Strict-Transport-Security"]
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts

    def test_permissions_policy(self):
        """Testa Permissions-Policy desabilita features sensíveis."""
        config = SecurityHeadersConfig()
        headers = config.to_dict()

        policy = headers["Permissions-Policy"]
        assert "geolocation=()" in policy
        assert "microphone=()" in policy
        assert "camera=()" in policy

    def test_custom_config(self):
        """Testa configuração customizada."""
        config = SecurityHeadersConfig(
            x_frame_options="SAMEORIGIN",
            content_security_policy="default-src 'self' https://cdn.example.com",
        )
        headers = config.to_dict()

        assert headers["X-Frame-Options"] == "SAMEORIGIN"
        assert "cdn.example.com" in headers["Content-Security-Policy"]

    def test_config_to_dict_has_all_headers(self):
        """Testa to_dict retorna todos os 7 headers."""
        config = SecurityHeadersConfig()
        headers = config.to_dict()

        expected_headers = {
            "X-Content-Type-Options",
            "X-Frame-Options",
            "Content-Security-Policy",
            "Strict-Transport-Security",
            "X-XSS-Protection",
            "Permissions-Policy",
            "Referrer-Policy",
        }

        assert set(headers.keys()) == expected_headers


class TestSecurityHeadersMiddleware:
    """Testes para middleware de headers de segurança."""

    @pytest.mark.asyncio()
    async def test_middleware_adds_security_headers(self):
        """Testa middleware adiciona headers de segurança."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/")
        async def root():
            return Response(content="OK", status_code=200)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "X-XSS-Protection" in response.headers

    @pytest.mark.asyncio()
    async def test_middleware_with_custom_config(self):
        """Testa middleware com configuração customizada."""
        custom_config = SecurityHeadersConfig(
            x_frame_options="SAMEORIGIN",
        )
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, config=custom_config)

        @app.get("/")
        async def root():
            return Response(content="OK")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert response.headers["X-Frame-Options"] == "SAMEORIGIN"

    @pytest.mark.asyncio()
    async def test_middleware_preserves_existing_headers(self):
        """Testa middleware não sobrescreve headers existentes."""
        from fastapi import Response

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/")
        async def root():
            return Response(
                content="OK",
                headers={
                    "X-Custom-Header": "custom-value",
                    "X-Frame-Options": "ALLOW-FROM",
                },
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert response.headers["X-Custom-Header"] == "custom-value"
        assert response.headers["X-Frame-Options"] == "ALLOW-FROM"

    @pytest.mark.asyncio()
    async def test_csp_header_present(self):
        """Testa CSP header está presente."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/")
        async def root():
            return Response(content="OK")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        csp = response.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp

    @pytest.mark.asyncio()
    async def test_hsts_header_present(self):
        """Testa HSTS header está presente."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/")
        async def root():
            return Response(content="OK")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        hsts = response.headers.get("Strict-Transport-Security", "")
        assert "max-age=31536000" in hsts

    @pytest.mark.asyncio()
    async def test_permissions_policy_header_present(self):
        """Testa Permissions-Policy header está presente."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/")
        async def root():
            return Response(content="OK")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        policy = response.headers.get("Permissions-Policy", "")
        assert len(policy) > 0

    @pytest.mark.asyncio()
    async def test_referrer_policy_header_present(self):
        """Testa Referrer-Policy header está presente."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/")
        async def root():
            return Response(content="OK")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert response.headers.get("Referrer-Policy") is not None


class TestAddSecurityHeadersHelper:
    """Testes para função helper add_security_headers."""

    @pytest.mark.asyncio()
    async def test_add_security_headers_helper(self):
        """Testa função helper adiciona middleware."""
        app = FastAPI()
        add_security_headers(app)

        @app.get("/")
        async def root():
            return Response(content="OK")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert response.headers.get("X-Content-Type-Options") is not None
        assert response.headers.get("X-Frame-Options") is not None

    @pytest.mark.asyncio()
    async def test_add_security_headers_with_custom_config(self):
        """Testa função helper com config customizada."""
        app = FastAPI()
        custom_config = SecurityHeadersConfig(
            x_content_type_options="nosniff",
        )
        add_security_headers(app, config=custom_config)

        @app.get("/")
        async def root():
            return Response(content="OK")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert response.headers["X-Content-Type-Options"] == "nosniff"


class TestSecurityHeadersIntegration:
    """Testes de integração com FastAPI."""

    @pytest.mark.asyncio()
    async def test_multiple_routes_have_security_headers(self):
        """Testa múltiplas rotas recebem headers de segurança."""
        app = FastAPI()
        add_security_headers(app)

        @app.get("/")
        async def root():
            return {"message": "root"}

        @app.get("/api/health")
        async def health():
            return {"status": "healthy"}

        @app.get("/api/v1/resource")
        async def resource():
            return {"data": "resource"}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for endpoint in ["/", "/api/health", "/api/v1/resource"]:
                response = await client.get(endpoint)
                assert "X-Content-Type-Options" in response.headers
                assert "X-Frame-Options" in response.headers

    @pytest.mark.asyncio()
    async def test_error_responses_have_security_headers(self):
        """Testa respostas de erro também têm headers de segurança."""
        from fastapi import HTTPException

        app = FastAPI()
        add_security_headers(app)

        @app.get("/not-found")
        async def not_found():
            raise HTTPException(status_code=404, detail="Not found")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/not-found")

        assert response.status_code == 404
        assert "X-Content-Type-Options" in response.headers
