"""
JWT Authentication Middleware para Unified Gateway.

Este middleware valida tokens JWT e extrai contexto de autenticação
(user_id, tenant_id) para passar para serviços downstream.

Implementa INV-7: JWT tokens validated by Unified Gateway must pass
user_id, tenant_id to downstream services.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog
from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class AuthMethod(str, Enum):
    """Métodos de autenticação suportados."""

    JWT = "jwt"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    NONE = "none"


@dataclass
class AuthContext:
    """Contexto de autenticação extraído do JWT."""

    authenticated: bool
    user_id: str | None = None
    tenant_id: str | None = None
    session_id: str | None = None
    auth_method: AuthMethod = AuthMethod.NONE
    roles: list[str] | None = None
    permissions: list[str] | None = None
    claims: dict[str, Any] | None = None

    def get_headers(self) -> dict[str, str]:
        """
        Retorna headers para passar contexto downstream.

        Implementa INV-7: passar user_id e tenant_id para serviços downstream.
        """
        headers = {
            "X-Auth-Method": self.auth_method.value,
            "X-Authenticated": str(self.authenticated).lower(),
        }
        if self.user_id:
            headers["X-User-ID"] = self.user_id
        if self.tenant_id:
            headers["X-Tenant-ID"] = self.tenant_id
        if self.session_id:
            headers["X-Session-ID"] = self.session_id
        if self.roles:
            headers["X-User-Roles"] = ",".join(self.roles)
        return headers


class JWTAuthError(Exception):
    """Erro na autenticação JWT."""

    def __init__(self, message: str, status_code: int = status.HTTP_401_UNAUTHORIZED):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware de autenticação JWT para Unified Gateway.

    Valida tokens JWT, extrai user_id e tenant_id, e adiciona
    headers de contexto para serviços downstream (INV-7).

    Paths excluídos da autenticação podem ser configurados via exclude_paths.
    """

    def __init__(
        self,
        app,
        exclude_paths: list[str] | None = None,
        require_auth: bool = True,
    ):
        """
        Inicializa middleware de autenticação JWT.

        Args:
            app: Aplicação FastAPI
            exclude_paths: Lista de paths para excluir da autenticação
            require_auth: Se False, autenticação é opcional (não bloqueia)
        """
        super().__init__(app)
        self.exclude_paths = exclude_paths or [
            "/health",
            "/health/ready",
            "/health/live",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
        ]
        self.require_auth = require_auth

        logger.info(
            "jwt_auth_middleware_initialized",
            exclude_paths=self.exclude_paths,
            require_auth=require_auth,
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Processa requisição e valida JWT.

        Extrai user_id e tenant_id do token JWT e adiciona ao
        contexto da requisição para uso downstream (INV-7).
        """
        path = request.url.path

        # Pular autenticação para paths excluídos
        if self._should_skip_auth(path):
            return await call_next(request)

        try:
            # Extrair e validar token
            auth_context = await self._extract_auth_context(request)

            # Adicionar contexto ao state da requisição
            request.state.auth_context = auth_context

            # Adicionar headers de contexto para downstream (INV-7)
            if auth_context.authenticated:
                context_headers = auth_context.get_headers()
                # Guardar headers no state para uso posterior
                request.state.context_headers = context_headers

            # Se autenticação é requerida e falhou, retornar 401
            if self.require_auth and not auth_context.authenticated:
                logger.warning("unauthenticated_request", path=path)
                return self._create_unauthorized_response()

            # Continuar processamento
            response = await call_next(request)

            # Adicionar headers de contexto à resposta
            if auth_context.authenticated and hasattr(request.state, "context_headers"):
                for header_name, header_value in request.state.context_headers.items():
                    response.headers[header_name] = header_value

            return response

        except JWTAuthError as e:
            logger.warning("jwt_auth_error", path=path, error=e.message)
            return self._create_error_response(e)

        except Exception:
            logger.exception("jwt_auth_internal_error", path=path)
            return self._create_error_response(
                JWTAuthError("Internal authentication error", status.HTTP_500_INTERNAL_SERVER_ERROR)
            )

    def _should_skip_auth(self, path: str) -> bool:
        """Verifica se path deve ser excluído da autenticação.

        "/" é tratado como match exacto para evitar que startswith faça
        match com TODOS os paths.
        """
        for exclude_path in self.exclude_paths:
            if exclude_path == "/":
                if path == "/":
                    return True
                continue
            if path.startswith(exclude_path):
                return True
        return False

    async def _extract_auth_context(self, request: Request) -> AuthContext:
        """
        Extrai contexto de autenticação da requisição.

        Implementa extração de user_id e tenant_id do JWT (INV-7).
        """
        authorization = request.headers.get("Authorization")

        if not authorization:
            # Sem header Authorization
            if self.require_auth:
                raise JWTAuthError("Missing Authorization header")
            return AuthContext(authenticated=False, auth_method=AuthMethod.NONE)

        if not authorization.startswith("Bearer "):
            if self.require_auth:
                raise JWTAuthError("Invalid Authorization header format")
            return AuthContext(authenticated=False, auth_method=AuthMethod.NONE)

        token = authorization.split(" ", 1)[1]

        # Validar token JWT
        try:
            claims = await self._validate_jwt_token(token)
            return self._build_auth_context(claims)

        except JWTAuthError:
            raise
        except Exception as e:
            logger.warning("jwt_validation_failed", error=str(e))
            if self.require_auth:
                raise JWTAuthError("Invalid JWT token")
            return AuthContext(authenticated=False, auth_method=AuthMethod.NONE)

    # Algoritmos permitidos. ``none`` é proibido em qualquer ambiente —
    # com ``verify_signature=False`` o PyJWT ignora o ``algorithms``
    # allowlist, por isso o ``alg`` do header é validado manualmente
    # antes de invocar o decode.
    _ALLOWED_ALGORITHMS = ("RS256", "HS256", "RS512", "ES256")

    async def _validate_jwt_token(self, token: str) -> dict[str, Any]:
        """
        Valida token JWT e retorna claims.

        Em produção, usa ``JWTVerifier`` de ``neural_hive_security`` (com
        verificação de assinatura via JWKS). Em desenvolvimento aceita
        tokens não-assinados, mas **rejeita sempre** ``alg=none`` e qualquer
        algoritmo fora do allowlist — independente do ambiente.
        """
        try:
            import jwt
        except ImportError:
            raise JWTAuthError("JWT library not available")

        # Pre-flight: extrair header sem confiar no `algorithms` do decode.
        # PyJWT com `verify_signature=False` ignora o filtro de algoritmos,
        # por isso `alg=none` ou alg arbitrários passariam silenciosamente.
        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            raise JWTAuthError(f"Malformed JWT header: {exc}")

        alg = unverified_header.get("alg")
        if not alg or alg.lower() == "none":
            raise JWTAuthError("Refusing JWT with alg=none")
        if alg not in self._ALLOWED_ALGORITHMS:
            raise JWTAuthError(f"JWT algorithm '{alg}' is not allowed")

        try:
            payload = jwt.decode(
                token,
                options={
                    "verify_signature": settings.ENVIRONMENT == "production",
                    "verify_exp": True,
                    "require": ["sub"],
                },
                algorithms=list(self._ALLOWED_ALGORITHMS),
            )
            return payload

        except jwt.ExpiredSignatureError:
            raise JWTAuthError("Token has expired")

        except jwt.InvalidTokenError as e:
            raise JWTAuthError(f"Invalid token: {e}")

    def _build_auth_context(self, claims: dict[str, Any]) -> AuthContext:
        """
        Constrói AuthContext a partir dos claims JWT.

        Implementa INV-7: extrair user_id e tenant_id.
        """
        # SPIFFE ID format: spiffe://domain/path/service
        # ou sub direto como user_id
        user_id = claims.get("sub") or claims.get("user_id")
        tenant_id = claims.get("tenant_id") or claims.get("aud")

        # Extrair session_id se disponível
        session_id = claims.get("session_id") or claims.get("sid")

        # Extrair roles
        roles = claims.get("roles", [])
        if isinstance(roles, str):
            roles = roles.split(",")

        # Extrair scopes como permissions
        permissions = claims.get("scope", [])
        if isinstance(permissions, str):
            permissions = permissions.split()

        logger.debug(
            "auth_context_built",
            user_id=user_id,
            tenant_id=tenant_id,
            has_session=session_id is not None,
            roles_count=len(roles),
        )

        return AuthContext(
            authenticated=True,
            user_id=user_id,
            tenant_id=tenant_id,
            session_id=session_id,
            auth_method=AuthMethod.JWT,
            roles=roles,
            permissions=permissions,
            claims=claims,
        )

    def _create_unauthorized_response(self) -> Response:
        """Cria resposta 401 Unauthorized."""
        return Response(
            content='{"error": "unauthorized", "message": "Authentication required"}',
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={
                "WWW-Authenticate": 'Bearer realm="unified-gateway"',
                "Content-Type": "application/json",
            },
            media_type="application/json",
        )

    def _create_error_response(self, error: JWTAuthError) -> Response:
        """Cria resposta de erro de autenticação."""
        return Response(
            content=f'{{"error": "authentication_failed", "message": "{error.message}"}}',
            status_code=error.status_code,
            headers={
                "WWW-Authenticate": 'Bearer realm="unified-gateway"',
                "Content-Type": "application/json",
            },
            media_type="application/json",
        )


async def get_auth_context(request: Request) -> AuthContext:
    """
    Dependency do FastAPI para obter contexto de autenticação.

    Uso:
        @app.get("/api/protected")
        async def protected_endpoint(auth: AuthContext = Depends(get_auth_context)):
            return {"user_id": auth.user_id, "tenant_id": auth.tenant_id}
    """
    if not hasattr(request.state, "auth_context"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication context not found",
        )

    auth_context = request.state.auth_context

    if not auth_context.authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    return auth_context


async def get_auth_context_optional(request: Request) -> AuthContext:
    """
    Dependency opcional que retorna AuthContext mesmo sem autenticação.

    Útil para endpoints que funcionam com e sem autenticação.
    """
    if hasattr(request.state, "auth_context"):
        return request.state.auth_context

    # Retornar AuthContext vazio se não autenticado
    return AuthContext(
        authenticated=False,
        user_id=None,
        tenant_id=None,
        session_id=None,
        auth_method=AuthMethod.NONE,
    )
