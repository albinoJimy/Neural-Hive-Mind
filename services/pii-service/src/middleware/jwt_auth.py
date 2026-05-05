"""JWT Authentication Middleware para PII Service."""

from typing import Callable
from datetime import datetime
from uuid import UUID

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt, jwk, JWTError, ExpiredSignatureError
from jose.exceptions import JWSError

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

        Valida JWT token usando python-jose (RS256 ou HS256).

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

        # Validar JWT token
        try:
            from src.config.settings import get_settings
            settings = get_settings()

            # Decodificar token
            if settings.JWKS_URL:
                # RS256 com JWKS (produção)
                claims = await self._validate_jwt_rs256(token, settings.JWKS_URL)
            else:
                # HS256 com secret (dev/staging)
                claims = self._validate_jwt_hs256(token, settings.JWT_SECRET)

            # Extrair claims padrão
            user_id = claims.get("sub") or claims.get("user_id")
            tenant_id = claims.get("tenant_id") or claims.get("tenantId")
            session_id = claims.get("session_id") or claims.get("sessionId")

            # Validar claims obrigatórios
            if not user_id:
                raise JWTError("Missing user_id (sub) claim")

            # Verificar expiração
            exp = claims.get("exp")
            if exp:
                exp_datetime = datetime.fromtimestamp(exp)
                if datetime.utcnow() > exp_datetime:
                    raise ExpiredSignatureError("Token expired")

            request.state.user_id = user_id
            request.state.tenant_id = tenant_id
            request.state.requestor_id = user_id
            request.state.session_id = session_id

            logger.debug(
                "jwt_authenticated",
                user_id=user_id,
                tenant_id=tenant_id,
                session_id=session_id,
            )

        except (JWTError, ExpiredSignatureError, JWSError) as e:
            logger.warning("jwt_validation_failed", error=str(e), error_type=type(e).__name__)
            if self.require_auth:
                error_msg = "Token expired" if isinstance(e, ExpiredSignatureError) else "Invalid JWT token"
                return Response(
                    content=f'{{"error": "{error_msg}"}}',
                    status_code=401,
                    media_type="application/json",
                )
            request.state.user_id = "anonymous"
            request.state.tenant_id = None
            request.state.requestor_id = "anonymous"
            request.state.session_id = None

        except Exception as e:
            logger.error("jwt_validation_error", error=str(e), error_type=type(e).__name__)
            if self.require_auth:
                return Response(
                    content='{"error": "Authentication failed"}',
                    status_code=500,
                    media_type="application/json",
                )
            request.state.user_id = "anonymous"
            request.state.tenant_id = None
            request.state.requestor_id = "anonymous"
            request.state.session_id = None

        return await call_next(request)

    def _validate_jwt_hs256(self, token: str, secret: str) -> dict:
        """
        Valida JWT token com HS256 (secret compartilhado).

        Args:
            token: JWT token
            secret: Segredo compartilhado

        Returns:
            Dict com claims
        """
        return jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
            }
        )

    async def _validate_jwt_rs256(self, token: str, jwks_url: str) -> dict:
        """
        Valida JWT token com RS256 (chave pública JWKS).

        Args:
            token: JWT token
            jwks_url: URL do JWKS endpoint

        Returns:
            Dict com claims
        """
        import httpx

        # Obter JWKS
        async with httpx.AsyncClient() as client:
            response = await client.get(jwks_url, timeout=5.0)
            response.raise_for_status()
            jwks = response.json()

        # Obter header do token para pegar kid
        headers = jwt.get_unverified_headers(token)
        kid = headers.get("kid")

        # Encontrar chave correta no JWKS
        rsa_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                rsa_key = jwk.construct(key)
                break

        if rsa_key is None:
            raise JWTError(f"Unable to find key with kid={kid}")

        # Validar token
        return jwt.decode(
            token,
            rsa_key.to_pem(),
            algorithms=["RS256"],
            audience="pii-service",
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_aud": True,
            }
        )
