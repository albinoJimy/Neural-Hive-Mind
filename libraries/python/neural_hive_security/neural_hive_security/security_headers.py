"""
Security Headers Middleware for FastAPI.

Este módulo fornece um middleware para adicionar headers de segurança HTTP
em todas as respostas dos serviços FastAPI do Neural Hive Mind.

Headers implementados:
- X-Content-Type-Options: Previne MIME-sniffing
- X-Frame-Options: Previne clickjacking
- Content-Security-Policy: Previne XSS
- Strict-Transport-Security: Força HTTPS
- X-XSS-Protection: Proteção XSS extra
- Permissions-Policy: Controla features do navegador
- Referrer-Policy: Controla informações de referer

Autor: Neural Hive Mind
Criado: 2026-04-19 (SEC-001)
"""

from dataclasses import dataclass
from typing import Mapping

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.base import Request as StarletteRequest
from starlette.types import ASGIApp


@dataclass(frozen=True)
class SecurityHeadersConfig:
    """Configuração dos headers de segurança."""

    x_content_type_options: str = "nosniff"
    x_frame_options: str = "DENY"
    content_security_policy: str = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
    )
    strict_transport_security: str = "max-age=31536000; includeSubDomains"
    x_xss_protection: str = "1; mode=block"
    permissions_policy: str = (
        "geolocation=(), "
        "microphone=(), "
        "camera=(), "
        "magnetometer=(), "
        "gyroscope=(), "
        "speaker=()"
    )
    referrer_policy: str = "strict-origin-when-cross-origin"

    def to_dict(self) -> Mapping[str, str]:
        """Converte configuração para dicionário de headers."""
        return {
            "X-Content-Type-Options": self.x_content_type_options,
            "X-Frame-Options": self.x_frame_options,
            "Content-Security-Policy": self.content_security_policy,
            "Strict-Transport-Security": self.strict_transport_security,
            "X-XSS-Protection": self.x_xss_protection,
            "Permissions-Policy": self.permissions_policy,
            "Referrer-Policy": self.referrer_policy,
        }


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware para adicionar headers de segurança HTTP.

    Este middleware adiciona headers de segurança em todas as respostas
    HTTP para proteger contra vulnerabilidades comuns da web.

    Uso:
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

    Ou com configuração customizada:
        config = SecurityHeadersConfig(
            content_security_policy="default-src 'self' https://cdn.example.com"
        )
        app.add_middleware(SecurityHeadersMiddleware, config=config)
    """

    def __init__(
        self,
        app: ASGIApp,
        config: SecurityHeadersConfig | None = None,
    ) -> None:
        """
        Inicializa o middleware de headers de segurança.

        Args:
            app: Aplicação ASGI (FastAPI)
            config: Configuração customizada (opcional)
        """
        super().__init__(app)
        self._config = config or SecurityHeadersConfig()
        self._headers = self._config.to_dict()

    async def dispatch(
        self,
        request: StarletteRequest,
        call_next,
    ) -> Response:
        """
        Processa request e adiciona headers de segurança na response.

        Args:
            request: Request HTTP
            call_next: Próximo middleware/rotina

        Returns:
            Response com headers de segurança adicionados
        """
        response = await call_next(request)

        # Adicionar headers de segurança
        for header_name, header_value in self._headers.items():
            # Não sobrescrever headers já definidos
            if header_name not in response.headers:
                response.headers[header_name] = header_value

        return response


def add_security_headers(
    app: FastAPI,
    config: SecurityHeadersConfig | None = None,
) -> None:
    """
    Adiciona middleware de headers de segurança à aplicação FastAPI.

    Função helper para facilitar integração.

    Args:
        app: Aplicação FastAPI
        config: Configuração customizada (opcional)

    Example:
        from fastapi import FastAPI
        from neural_hive_security.security_headers import add_security_headers

        app = FastAPI()
        add_security_headers(app)
    """
    app.add_middleware(SecurityHeadersMiddleware, config=config)


__all__ = [
    "SecurityHeadersConfig",
    "SecurityHeadersMiddleware",
    "add_security_headers",
]
