"""
Security Headers Middleware for FastAPI.

Adds security-related HTTP headers to all responses to protect against
common web vulnerabilities (XSS, clickjacking, MIME-sniffing, etc).
"""

from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware para adicionar headers de segurança HTTP em todas as respostas.

    Headers adicionados:
    - X-Content-Type-Options: nosniff (previne MIME-sniffing)
    - X-Frame-Options: DENY (previne clickjacking)
    - Content-Security-Policy: Restrições de conteúdo (previne XSS)
    - Strict-Transport-Security: Força HTTPS (HSTS)
    - X-XSS-Protection: Proteção XSS extra para navegadores antigos
    - Referrer-Policy: Controla informações de referer
    - Permissions-Policy: Controla features do navegador

    Args:
        csp_include_unsafe_inline: Se True, permite 'unsafe-inline' em CSP
                                   (necessário para some inline scripts/styles)
        hsts_include_subdomains: Se True, inclui subdomínios no HSTS
        hsts_preload: Se True, adiciona flag preload ao HSTS
    """

    def __init__(
        self,
        app: Callable,
        csp_include_unsafe_inline: bool = True,
        hsts_include_subdomains: bool = True,
        hsts_preload: bool = False,
    ):
        """
        Inicializa o middleware.

        Args:
            app: Aplicação FastAPI/Starlette
            csp_include_unsafe_inline: Permitir inline scripts/styles em CSP
            hsts_include_subdomains: Incluir subdomínios no HSTS
            hsts_preload: Adicionar flag preload ao HSTS
        """
        super().__init__(app)
        self.csp_include_unsafe_inline = csp_include_unsafe_inline
        self.hsts_include_subdomains = hsts_include_subdomains
        self.hsts_preload = hsts_preload

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Processa o request e adiciona headers de segurança à response.

        Args:
            request: Request HTTP recebido
            call_next: Próximo middleware/rotina na cadeia

        Returns:
            Response com headers de segurança adicionados
        """
        response = await call_next(request)

        # X-Content-Type-Options: previne MIME-sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # X-Frame-Options: previne clickjacking (DENY = não permite framing)
        response.headers["X-Frame-Options"] = "DENY"

        # Content-Security-Policy: previne XSS e data injection attacks
        csp = self._build_csp()
        response.headers["Content-Security-Policy"] = csp

        # Strict-Transport-Security: força HTTPS (HSTS)
        hsts = self._build_hsts()
        response.headers["Strict-Transport-Security"] = hsts

        # X-XSS-Protection: proteção XSS extra para browsers antigos
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer-Policy: controla informações de referer em navegação
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions-Policy (antigo Feature-Policy): controla features do navegador
        permissions_policy = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "accelerometer=()"
        )
        response.headers["Permissions-Policy"] = permissions_policy

        # X-Permitted-Cross-Domain-Policies: restringe cross-domain policies (Adobe Flash)
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        # Cross-Origin-Opener-Policy: isolata contexto de navegação
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

        # Cross-Origin-Resource-Policy: protege recursos de cross-origin
        response.headers["Cross-Origin-Resource-Policy"] = "same-site"

        return response

    def _build_csp(self) -> str:
        """
        Constrói a Directiva Content-Security-Policy.

        Returns:
            String com a política CSP
        """
        # Directivas base
        csp_parts = ["default-src 'self'"]

        # Para desenvolvimento, pode precisar permitir inline
        if self.csp_include_unsafe_inline:
            csp_parts.append("script-src 'self' 'unsafe-inline' 'unsafe-eval'")
            csp_parts.append("style-src 'self' 'unsafe-inline'")
        else:
            csp_parts.append("script-src 'self'")
            csp_parts.append("style-src 'self'")

        # Permitir imagens de qualquer origem (comum para avatars, etc)
        csp_parts.append("img-src 'self' data: https:")

        # Permitir conexões WebSocket para mesma origem
        csp_parts.append("connect-src 'self'")

        # Permitir iframes de mesma origem (mas X-Frame-Options já é DENY)
        csp_parts.append("frame-src 'self'")

        # Fontes de mesma origem
        csp_parts.append("font-src 'self'")

        # Objetos (flash, plugins) bloqueados
        csp_parts.append("object-src 'none'")

        # Base URI não pode ser definida dinamicamente
        csp_parts.append("base-uri 'self'")

        # Form actions apenas para mesma origem
        csp_parts.append("form-action 'self'")

        # Upgrade requests inseguros para HTTPS
        csp_parts.append("upgrade-insecure-requests")

        return "; ".join(csp_parts)

    def _build_hsts(self) -> str:
        """
        Constrói a Directiva HTTP Strict Transport Security (HSTS).

        Returns:
            String com a política HSTS
        """
        # 1 ano = 31536000 segundos
        hsts = "max-age=31536000"

        if self.hsts_include_subdomains:
            hsts += "; includeSubDomains"

        if self.hsts_preload:
            hsts += "; preload"

        return hsts


class SecurityHeadersMiddlewareConfig:
    """
    Configuração para o SecurityHeadersMiddleware.

    Permite customização dos headers via settings do serviço.
    """

    def __init__(
        self,
        csp_include_unsafe_inline: bool = True,
        hsts_include_subdomains: bool = True,
        hsts_preload: bool = False,
        custom_headers: dict[str, str] | None = None,
    ):
        """
        Inicializa a configuração.

        Args:
            csp_include_unsafe_inline: Permitir inline scripts/styles em CSP
            hsts_include_subdomains: Incluir subdomínios no HSTS
            hsts_preload: Adicionar flag preload ao HSTS
            custom_headers: Headers customizados adicionais
        """
        self.csp_include_unsafe_inline = csp_include_unsafe_inline
        self.hsts_include_subdomains = hsts_include_subdomains
        self.hsts_preload = hsts_preload
        self.custom_headers = custom_headers or {}

    def as_kwargs(self) -> dict:
        """
        Retorna kwargs para inicialização do middleware.

        Returns:
            Dict com kwargs
        """
        return {
            "csp_include_unsafe_inline": self.csp_include_unsafe_inline,
            "hsts_include_subdomains": self.hsts_include_subdomains,
            "hsts_preload": self.hsts_preload,
        }
