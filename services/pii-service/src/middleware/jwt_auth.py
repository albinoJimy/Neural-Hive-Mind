"""JWT Authentication Middleware para PII Service."""

from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

import structlog

logger = structlog.get_logger(__name__)


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware para autenticação JWT (R-P4: JWT auth required).

    Extrai user_id e tenant_id do token JWT e adiciona ao state da request.
    """

    def __init__(
        self,
        app,
        exclude_paths: list[str] | None = None,
        require_auth: bool = True,
    ):
        """
        Inicializa middleware.

        Args:
            app: Aplicação FastAPI
            exclude_paths: Paths que não requerem autenticação
            require_auth: Se autenticação é obrigatória (R-P4)
        """
        super().__init__(app)
        self.exclude_paths = set(exclude_paths or [])
        self.require_auth = require_auth

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Processa request e adiciona contexto de autenticação.

        Args:
            request: Request FastAPI
            call_next: Próximo middleware/handler

        Returns:
            Response
        """
        # Verificar se path está excluído
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Extrair token Authorization header
        authorization = request.headers.get("Authorization")

        if not authorization:
            if self.require_auth:
                return Response(
                    content='{"error": "Authorization header required"}',
                    status_code=401,
                    media_type="application/json",
                )
            # Auth não obrigatória - continuar com usuário anônimo
            request.state.user_id = "anonymous"
            request.state.tenant_id = None
            request.state.requestor_id = "anonymous"
            return await call_next(request)

        # Validar formato Bearer
        if not authorization.startswith("Bearer "):
            if self.require_auth:
                return Response(
                    content='{"error": "Invalid authorization format"}',
                    status_code=401,
                    media_type="application/json",
                )
            request.state.user_id = "anonymous"
            request.state.tenant_id = None
            request.state.requestor_id = "anonymous"
            return await call_next(request)

        token = authorization[7:]

        # TODO: Implementar validação JWT real
        # Por enquanto, extrair informações básicas
        # Em produção, usar python-jose ou similar para validar

        try:
            # Placeholder - em produção, validar JWT
            # claims = validate_jwt(token)
            # user_id = claims.get("sub")
            # tenant_id = claims.get("tenant_id")

            # Por enquanto, usar token como user_id
            user_id = f"user:{token[:8]}"
            tenant_id = None  # Extrair do claims

            request.state.user_id = user_id
            request.state.tenant_id = tenant_id
            request.state.requestor_id = user_id

            logger.debug("jwt_authenticated", user_id=user_id, tenant_id=tenant_id)

        except Exception as e:
            logger.warning("jwt_validation_failed", error=str(e))
            if self.require_auth:
                return Response(
                    content='{"error": "Invalid JWT token"}',
                    status_code=401,
                    media_type="application/json",
                )
            request.state.user_id = "anonymous"
            request.state.tenant_id = None
            request.state.requestor_id = "anonymous"

        return await call_next(request)
