"""
FastAPI Middleware for OPA Authorization.

Este módulo fornece middlewares FastAPI para autorização
via Open Policy Agent (OPA) usando a biblioteca neural_hive_opa.

Uso básico:
    from fastapi import FastAPI
    from neural_hive_opa.middleware import OPAAuthorizationMiddleware, opa_dependency

    app = FastAPI()

    # Adicionar middleware global
    app.add_middleware(
        OPAAuthorizationMiddleware,
        opa_url="http://opa:8181",
        policy_path="neuralhive/authz"
    )

    # Ou usar como dependency em rotas específicas
    @app.get("/api/resource")
    async def get_resource(authz: dict = Depends(opopa_dependency)):
        return {"data": "authorized"}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

from fastapi import Request, Response, status
from fastapi.dependencies.utils import get_dependant
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from neural_hive_opa import OPAConfig, OPAClient, OPAConnectionError, OPAEvaluationError

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class OPAMiddlewareConfig:
    """Configuração para o middleware OPA."""

    opa_url: str = "http://localhost:8181"
    policy_path: str = "neuralhive/authz"
    timeout_seconds: int = 5
    cache_ttl_seconds: int = 300
    decision_id_header: str = "X-Decision-ID"

    # Comportamento em caso de erro
    fail_open: bool = False  # Se True, permite acesso quando OPA falha

    # Headers para extrair contexto da requisição
    user_id_header: str = "X-User-ID"
    tenant_id_header: str = "X-Tenant-ID"
    role_header: str = "X-User-Role"

    # Configurações de circuit breaker
    circuit_breaker_enabled: bool = True
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_timeout_seconds: int = 60


class OPAAuthorizationMiddleware(BaseHTTPMiddleware):
    """
    Middleware FastAPI para autorização via OPA.

    Este middleware intercepta todas as requisições HTTP e avalia
    políticas OPA para determinar se o acesso deve ser permitido.

    Exemplo:
        app = FastAPI()
        app.add_middleware(
            OPAAuthorizationMiddleware,
            opa_url="http://opa:8181",
            policy_path="neuralhive/authz"
        )
    """

    def __init__(
        self,
        app: ASGIApp,
        opa_url: str | None = None,
        policy_path: str | None = None,
        config: OPAMiddlewareConfig | None = None,
    ) -> None:
        """
        Inicializa o middleware OPA.

        Args:
            app: Aplicação ASGI (FastAPI)
            opa_url: URL do servidor OPA
            policy_path: Caminho da política OPA
            config: Configuração completa (sobrescreve opa_url e policy_path)
        """
        super().__init__(app)

        self.config = config or OPAMiddlewareConfig()

        if opa_url:
            self.config.opa_url = opa_url
        if policy_path:
            self.config.policy_path = policy_path

        # Criar cliente OPA
        opa_config = OPAConfig(
            opa_url=self.config.opa_url,
            opa_timeout_seconds=self.config.timeout_seconds,
            opa_cache_ttl_seconds=self.config.cache_ttl_seconds,
            opa_circuit_breaker_enabled=self.config.circuit_breaker_enabled,
            opa_circuit_breaker_failure_threshold=self.config.circuit_breaker_failure_threshold,
            opa_circuit_breaker_reset_timeout_seconds=self.config.circuit_breaker_reset_timeout_seconds,
        )
        self._client = OPAClient(config=opa_config, metrics=None)
        self._initialized = False

    async def _build_opa_input(self, request: Request) -> dict[str, Any]:
        """
        Constrói o input para avaliação OPA.

        Args:
            request: Requisição HTTP

        Returns:
            Dict com input formatado para OPA
        """
        # Headers de contexto
        user_id = request.headers.get(self.config.user_id_header, "anonymous")
        tenant_id = request.headers.get(self.config.tenant_id_header, "default")
        role = request.headers.get(self.config.role_header, "guest")

        # Extrair informações da requisição
        input_data: dict[str, Any] = {
            "user": {
                "id": user_id,
                "tenant_id": tenant_id,
                "role": role,
            },
            "request": {
                "method": request.method,
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "headers": dict(request.headers),
            },
        }

        # Adicionar body para métodos que não são GET/HEAD
        if request.method in {"POST", "PUT", "PATCH"}:
            try:
                # Tentar ler JSON body
                body = await request.json()
                input_data["request"]["body"] = body
            except Exception:
                # Se não for JSON, usar string vazia
                input_data["request"]["body"] = None

        return input_data

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """
        Processa a requisição através do middleware.

        Args:
            request: Requisição HTTP
            call_next: Próximo middleware/rota na chain

        Returns:
            Response HTTP
        """
        # Inicializar cliente se necessário
        if not self._initialized:
            await self._client.initialize()
            self._initialized = True

        # Caminhos que devem ser ignorados (health check, metrics, etc.)
        if self._should_skip_path(request.url.path):
            return await call_next(request)

        # Construir input OPA
        try:
            opa_input = await self._build_opa_input(request)
        except Exception as e:
            logger.error("failed_to_build_opa_input", error=str(e))
            return self._create_denied_response(
                detail="Failed to build authorization context",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Avaliar política OPA
        try:
            result = await self._client.evaluate(
                self.config.policy_path,
                opa_input
            )
        except OPAConnectionError as e:
            logger.error("opa_connection_failed", error=str(e))
            if self.config.fail_open:
                return await call_next(request)
            return self._create_denied_response(
                detail="Authorization service unavailable",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except OPAPolicyNotFoundError as e:
            logger.warning("opa_policy_not_found", policy_path=self.config.policy_path)
            if self.config.fail_open:
                return await call_next(request)
            return self._create_denied_response(
                detail="Authorization policy not found",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except OPAEvaluationError as e:
            logger.error("opa_evaluation_failed", error=str(e))
            if self.config.fail_open:
                return await call_next(request)
            return self._create_denied_response(
                detail="Authorization evaluation failed",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            logger.exception("unexpected_opa_error", error=str(e))
            if self.config.fail_open:
                return await call_next(request)
            return self._create_denied_response(
                detail="Unexpected authorization error",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Verificar decisão OPA
        allow = result.get("allow", False)

        if not allow:
            logger.info("access_denied", path=request.url.path, user=opa_input.get("user", {}).get("id"))
            return self._create_denied_response(
                detail=result.get("reason", "Access denied"),
                decision_id=result.get("decision_id"),
            )

        # Adicionar headers de decisão à resposta
        response = await call_next(request)
        if hasattr(response, "headers"):
            decision_id = result.get("decision_id")
            if decision_id:
                response.headers[self.config.decision_id_header] = decision_id

        return response

    def _should_skip_path(self, path: str) -> bool:
        """
        Verifica se o path deve ser ignorado pelo middleware.

        Args:
            path: Caminho da requisição

        Returns:
            True se deve pular autorização
        """
        skip_paths = {
            "/health",
            "/healthz",
            "/ready",
            "/metrics",
            "/openapi.json",
            "/docs",
            "/redoc",
        }

        # Path exato
        if path in skip_paths:
            return True

        # Path com prefixo
        return any(path.startswith(prefix) for prefix in ["/static", "/favicon"])

    def _create_denied_response(
        self,
        detail: str,
        status_code: int = status.HTTP_403_FORBIDDEN,
        decision_id: str | None = None,
    ) -> Response:
        """
        Cria uma resposta de acesso negado.

        Args:
            detail: Mensagem de erro
            status_code: Código HTTP
            decision_id: ID da decisão OPA (opcional)

        Returns:
            Response HTTP
        """
        import json

        content = {"detail": detail, "allowed": False}
        if decision_id:
            content["decision_id"] = decision_id

        return Response(
            content=json.dumps(content),
            status_code=status_code,
            media_type="application/json",
        )


# Classe para dependency injection em FastAPI
@dataclass
class OPADependency:
    """
    Dependency do FastAPI para autorização OPA em rotas específicas.

    Útil quando você quer autorização seletiva em algumas rotas
    em vez de middleware global.

    Exemplo:
        from fastapi import Depends, FastAPI
        from neural_hive_opa.middleware import OPADependency

        app = FastAPI()
        opa_auth = OPADependency(
            opa_url="http://opa:8181",
            policy_path="neuralhive/resource"
        )

        @app.get("/api/resource/{resource_id}")
        async def get_resource(
            resource_id: str,
            authz: dict = Depends(opa_auth)
        ):
            return {"resource_id": resource_id}
    """

    def __init__(
        self,
        opa_url: str = "http://localhost:8181",
        policy_path: str = "neuralhive/authz",
        timeout_seconds: int = 5,
        fail_open: bool = False,
    ) -> None:
        """
        Inicializa a dependency OPA.

        Args:
            opa_url: URL do servidor OPA
            policy_path: Caminho da política OPA
            timeout_seconds: Timeout em segundos
            fail_open: Se True, permite acesso quando OPA falha
        """
        self.opa_url = opa_url
        self.policy_path = policy_path
        self.timeout_seconds = timeout_seconds
        self.fail_open = fail_open
        self._client: OPAClient | None = None

    async def _get_client(self) -> OPAClient:
        """Retorna cliente OPA inicializado."""
        if self._client is None:
            opa_config = OPAConfig(
                opa_url=self.opa_url,
                opa_timeout_seconds=self.timeout_seconds,
                opa_cache_ttl_seconds=300,
                opa_circuit_breaker_enabled=True,
            )
            self._client = OPAClient(config=opa_config, metrics=None)
            await self._client.initialize()
        return self._client

    async def __call__(
        self,
        request: Request,
    ) -> dict[str, Any]:
        """
        Avalia autorização para a requisição atual.

        Args:
            request: Requisição FastAPI

        Returns:
            Dict com resultado da autorização

        Raises:
            HTTPException: Se acesso for negado
        """
        from fastapi import HTTPException

        client = await self._get_client()

        # Construir input OPA
        opa_input: dict[str, Any] = {
            "user": {
                "id": request.headers.get("X-User-ID", "anonymous"),
                "tenant_id": request.headers.get("X-Tenant-ID", "default"),
                "role": request.headers.get("X-User-Role", "guest"),
            },
            "request": {
                "method": request.method,
                "path": request.url.path,
                "query_params": dict(request.query_params),
            },
        }

        # Avaliar política
        try:
            result = await client.evaluate(self.policy_path, opa_input)
        except Exception as e:
            logger.error("opa_dependency_error", error=str(e))
            if self.fail_open:
                return {"allow": True, "source": "fail_open"}
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authorization service unavailable"
            )

        if not result.get("allow", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=result.get("reason", "Access denied")
            )

        return result


__all__ = [
    "OPAAuthorizationMiddleware",
    "OPAMiddlewareConfig",
    "OPADependency",
]
