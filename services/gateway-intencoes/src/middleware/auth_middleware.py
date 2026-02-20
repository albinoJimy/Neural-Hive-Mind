"""
Middleware de Autenticação OAuth2 + mTLS para Neural Hive-Mind
Integra validação JWT com certificados cliente
"""

import logging
from typing import Optional, Dict, Any, List
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from opentelemetry import trace

from security.oauth2_validator import get_oauth2_validator, TokenValidationError
from config.settings import get_settings

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

security = HTTPBearer(auto_error=False)


class AuthenticationError(Exception):
    """Erro de autenticação customizado"""

    def __init__(self, message: str, status_code: int = status.HTTP_401_UNAUTHORIZED):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware de autenticação híbrida OAuth2 + mTLS"""

    def __init__(
        self, app, exclude_paths: Optional[List[str]] = None, rate_limiter=None
    ):
        super().__init__(app)
        self.settings = get_settings()
        self.rate_limiter = rate_limiter  # Injetar rate limiter
        self.exclude_paths = exclude_paths or [
            "/health",
            "/ready",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/auth/callback",
        ]

    async def dispatch(self, request: Request, call_next):
        """Processar autenticação na requisição"""

        # Pular autenticação para paths excluídos
        if self._should_skip_auth(request.url.path):
            return await call_next(request)

        # Não aplicar autenticação se desabilitada
        if not self.settings.token_validation_enabled:
            logger.debug("Validação de token desabilitada")
            return await call_next(request)

        try:
            with tracer.start_as_current_span("auth_middleware"):
                # 1. Extrair e validar token JWT
                user_context = await self._validate_jwt_token(request)

                # 2. Validar certificado mTLS (opcional)
                mtls_context = await self._validate_mtls_certificate(request)

                # 3. Enriquecer contexto da requisição
                request.state.user = user_context
                request.state.mtls = mtls_context
                request.state.authenticated = True

                # 4. Adicionar headers de contexto
                self._add_context_headers(request, user_context, mtls_context)

                logger.info(
                    f"Usuário autenticado: {user_context.get('username')} "
                    f"via {'JWT+mTLS' if mtls_context else 'JWT'}"
                )

                # 5. Processar requisição e capturar resposta
                response = await call_next(request)

                # 6. Adicionar headers de rate limit à resposta de sucesso
                response = self._add_rate_limit_headers_to_response(request, response)

                return response

        except AuthenticationError as e:
            logger.warning(
                f"Falha na autenticação para {request.url.path}: {e.message}"
            )
            return self._create_auth_error_response(e, request)

        except Exception as e:
            logger.error(f"Erro interno na autenticação: {e}")
            return self._create_auth_error_response(
                AuthenticationError(
                    "Erro interno de autenticação",
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                ),
                request,
            )

    def _should_skip_auth(self, path: str) -> bool:
        """Verificar se deve pular autenticação para o path"""
        return any(path.startswith(exclude_path) for exclude_path in self.exclude_paths)

    async def _validate_jwt_token(self, request: Request) -> Dict[str, Any]:
        """Validar token JWT OAuth2"""

        # Extrair token do header Authorization
        authorization = request.headers.get("Authorization")
        if not authorization:
            raise AuthenticationError("Header Authorization obrigatório")

        if not authorization.startswith("Bearer "):
            raise AuthenticationError("Token deve usar formato Bearer")

        token = authorization.split(" ", 1)[1]

        try:
            # Validar token com Keycloak
            validator = await get_oauth2_validator()

            # Determinar scopes obrigatórios baseados no endpoint
            required_scopes = self._get_required_scopes(
                request.url.path, request.method
            )

            # Validar token completo
            payload = await validator.validate_token(
                token=token,
                required_scopes=required_scopes,
                client_id=self.settings.keycloak_client_id,
            )

            # Extrair contexto do usuário
            user_context = validator.extract_user_context(payload)

            # Validações adicionais por endpoint
            await self._validate_endpoint_access(request, user_context)

            return user_context

        except TokenValidationError as e:
            raise AuthenticationError(f"Token inválido: {e}")

    async def _validate_mtls_certificate(
        self, request: Request
    ) -> Optional[Dict[str, Any]]:
        """Validar certificado mTLS (opcional)"""
        try:
            # Extrair informações do certificado cliente
            client_cert = request.headers.get("X-SSL-Client-Cert")
            if not client_cert:
                return None

            # Headers padrão nginx/istio para mTLS
            cert_subject = request.headers.get("X-SSL-Client-Subject")
            cert_issuer = request.headers.get("X-SSL-Client-Issuer")
            cert_fingerprint = request.headers.get("X-SSL-Client-Fingerprint")
            cert_verified = request.headers.get("X-SSL-Client-Verify")

            if cert_verified != "SUCCESS":
                logger.warning("Certificado cliente não verificado")
                return None

            mtls_context = {
                "verified": True,
                "subject": cert_subject,
                "issuer": cert_issuer,
                "fingerprint": cert_fingerprint,
                "source": "istio-gateway",
            }

            logger.debug(f"Certificado mTLS validado: {cert_subject}")
            return mtls_context

        except Exception as e:
            logger.warning(f"Erro na validação mTLS: {e}")
            return None

    def _get_required_scopes(self, path: str, method: str) -> List[str]:
        """Determinar scopes obrigatórios por endpoint"""

        # Mapeamento de endpoints para scopes
        scope_mappings = {
            "/intentions": {
                "GET": ["read:intentions"],
                "POST": ["write:intentions"],
                "PUT": ["write:intentions"],
                "DELETE": ["delete:intentions"],
            },
            "/api/v1/admin": {"*": ["admin:access"]},
            "/api/v1/internal": {"*": ["internal:access"]},
        }

        # Verificar mapeamentos específicos
        for endpoint_pattern, methods in scope_mappings.items():
            if path.startswith(endpoint_pattern):
                return methods.get(method, methods.get("*", []))

        # Scopes padrão para APIs protegidas
        if path.startswith("/api/"):
            return ["neural-hive:access"]

        return []

    async def _validate_endpoint_access(
        self, request: Request, user_context: Dict[str, Any]
    ):
        """Validar acesso específico por endpoint"""
        path = request.url.path
        method = request.method
        user_roles = user_context.get("roles", [])

        # Endpoints administrativos
        if "/admin" in path and "neural-hive-admin" not in user_roles:
            raise AuthenticationError("Acesso negado: requer role admin")

        # Endpoints internos - apenas service accounts
        if "/internal" in path:
            if not user_context.get("client_id", "").startswith("service-"):
                raise AuthenticationError("Acesso negado: endpoint interno")

        # Rate limiting por usuário
        user_id = user_context.get("user_id")
        tenant_id = user_context.get("tenant_id") or user_context.get("client_id")

        if user_id and self.rate_limiter:
            rate_limit_result = await self.rate_limiter.check_rate_limit(
                user_id=user_id, tenant_id=tenant_id, endpoint=path
            )

            # Armazenar headers de rate limit para adicionar na resposta
            request.state.rate_limit_headers = {
                "X-RateLimit-Limit": str(rate_limit_result.limit),
                "X-RateLimit-Remaining": str(rate_limit_result.remaining),
                "X-RateLimit-Reset": str(rate_limit_result.reset_at),
            }

            if not rate_limit_result.allowed:
                raise AuthenticationError(
                    f"Rate limit excedido. Tente novamente em {rate_limit_result.retry_after}s",
                    status.HTTP_429_TOO_MANY_REQUESTS,
                )

    def _add_context_headers(
        self,
        request: Request,
        user_context: Dict[str, Any],
        mtls_context: Optional[Dict[str, Any]],
    ):
        """Adicionar headers de contexto para downstream services"""

        # Headers do usuário
        request.state.context_headers = {
            "X-User-ID": user_context.get("user_id", ""),
            "X-Username": user_context.get("username", ""),
            "X-User-Email": user_context.get("email", ""),
            "X-User-Roles": ",".join(user_context.get("roles", [])),
            "X-Client-ID": user_context.get("client_id", ""),
            "X-Session-ID": user_context.get("session_id", ""),
            "X-Auth-Method": "oauth2-jwt",
        }

        # Headers mTLS se disponível
        if mtls_context and mtls_context.get("verified"):
            request.state.context_headers.update(
                {
                    "X-mTLS-Verified": "true",
                    "X-mTLS-Subject": mtls_context.get("subject", ""),
                    "X-mTLS-Fingerprint": mtls_context.get("fingerprint", ""),
                    "X-Auth-Method": "oauth2-jwt+mtls",
                }
            )

    def _add_rate_limit_headers_to_response(
        self, request: Request, response: Response
    ) -> Response:
        """Adicionar headers de rate limit à resposta de sucesso"""
        if hasattr(request, "state") and hasattr(request.state, "rate_limit_headers"):
            rate_limit_headers = request.state.rate_limit_headers
            if rate_limit_headers:
                for header_name, header_value in rate_limit_headers.items():
                    response.headers[header_name] = header_value
        return response

    def _create_auth_error_response(
        self, error: AuthenticationError, request: Optional[Request] = None
    ) -> Response:
        """Criar resposta de erro de autenticação"""
        import re

        headers = {
            "WWW-Authenticate": f'Bearer realm="{self.settings.keycloak_realm}"',
            "X-Auth-Error": error.message,
        }

        # Adicionar headers de rate limit se disponíveis
        if (
            request
            and hasattr(request, "state")
            and hasattr(request.state, "rate_limit_headers")
        ):
            headers.update(request.state.rate_limit_headers)

        # Se erro 429, adicionar Retry-After header
        if error.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            match = re.search(r"(\d+)s", error.message)
            if match:
                headers["Retry-After"] = match.group(1)

        # Adicionar informações de debugging em desenvolvimento
        if self.settings.environment == "dev":
            headers["X-Keycloak-URL"] = self.settings.keycloak_url
            headers["X-JWKS-URI"] = self.settings.jwks_uri

        return Response(
            content=f'{{"error": "authentication_failed", "message": "{error.message}"}}',
            status_code=error.status_code,
            headers=headers,
            media_type="application/json",
        )


async def get_current_user(request: Request) -> Dict[str, Any]:
    """Dependency para obter usuário atual autenticado"""
    if not hasattr(request.state, "authenticated") or not request.state.authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não autenticado"
        )

    return request.state.user


async def get_current_admin_user(request: Request) -> Dict[str, Any]:
    """Dependency para obter usuário admin autenticado"""
    user = await get_current_user(request)

    if not user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: requer role admin",
        )

    return user


async def require_scopes(required_scopes: List[str]):
    """Dependency factory para validar scopes específicos"""

    async def _check_scopes(request: Request) -> Dict[str, Any]:
        user = await get_current_user(request)
        user_scopes = user.get("scopes", [])

        missing_scopes = set(required_scopes) - set(user_scopes)
        if missing_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Scopes insuficientes: faltando {list(missing_scopes)}",
            )

        return user

    return _check_scopes


class OptionalAuthMiddleware(BaseHTTPMiddleware):
    """Middleware de autenticação opcional (não bloqueia se não autenticado)"""

    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings()

    async def dispatch(self, request: Request, call_next):
        """Processar autenticação opcional"""

        request.state.authenticated = False
        request.state.user = None

        authorization = request.headers.get("Authorization")
        if authorization and authorization.startswith("Bearer "):
            try:
                token = authorization.split(" ", 1)[1]
                validator = await get_oauth2_validator()
                payload = await validator.validate_token(token)

                request.state.user = validator.extract_user_context(payload)
                request.state.authenticated = True

            except Exception as e:
                logger.debug(f"Autenticação opcional falhou: {e}")

        return await call_next(request)


def create_auth_middleware(
    exclude_paths: Optional[List[str]] = None, optional: bool = False, rate_limiter=None
) -> BaseHTTPMiddleware:
    """Factory para criar middleware de autenticação"""

    if optional:
        return OptionalAuthMiddleware

    def middleware_factory(app):
        # Se rate_limiter nao foi passado, tentar obter do singleton
        rl = rate_limiter
        if rl is None:
            from middleware.rate_limiter import get_rate_limiter

            rl = get_rate_limiter()
        return AuthMiddleware(app, exclude_paths, rate_limiter=rl)

    return middleware_factory
