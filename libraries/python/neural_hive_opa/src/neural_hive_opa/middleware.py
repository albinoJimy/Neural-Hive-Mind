"""
Middleware de autorização OPA para FastAPI.

Intercepta requisições HTTP e valida autorização via Open Policy Agent.
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import structlog
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from neural_hive_opa.client import OPAClient, OPAClientConfig

logger = structlog.get_logger()


# Métricas Prometheus
opa_middleware_decisions_total = Counter(
    "opa_middleware_decisions_total",
    "Total de decisões do middleware OPA",
    ["decision", "cached"],
)

opa_middleware_latency_seconds = Histogram(
    "opa_middleware_latency_seconds",
    "Latência do middleware OPA",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

opa_middleware_cache_hits_total = Counter(
    "opa_middleware_cache_hits_total",
    "Total de cache hits do middleware OPA",
)

opa_middleware_circuit_breaker_open = Gauge(
    "opa_middleware_circuit_breaker_open",
    "Indica se o circuit breaker do OPA está aberto (1=sim, 0=não)",
)

opa_middleware_opa_unavailable_total = Counter(
    "opa_middleware_opa_unavailable_total",
    "Total de vezes que OPA estava indisponível",
)


@dataclass
class OPAMiddlewareConfig:
    """Configuração do middleware OPA."""

    opa_url: str
    policy_path: str = "neuralhive/orchestrator/authz"
    timeout_seconds: int = 5
    fail_open: bool = False
    enable_cache: bool = True
    cache_ttl_seconds: int = 300

    # Headers de autenticação
    user_id_header: str = "X-User-ID"
    tenant_id_header: str = "X-Tenant-ID"
    role_header: str = "X-User-Role"

    # Paths públicos
    public_paths: list[str] = field(
        default_factory=lambda: [
            "/health",
            "/healthz",
            "/ready",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
            "/static",
        ]
    )

    # Circuit breaker
    circuit_breaker_enabled: bool = True
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_timeout: int = 60

    # Métricas
    metrics_enabled: bool = True
    metrics_service_name: str = "orchestrator"


class OPAAuthorizationMiddleware(BaseHTTPMiddleware):
    """
    Middleware de autorização OPA para FastAPI.

    Intercepta todas as requisições HTTP e valida autorização via OPA.

    Exemplo:
        ```python
        from fastapi import FastAPI
        from neural_hive_opa import OPAAuthorizationMiddleware, OPAMiddlewareConfig

        app = FastAPI()
        app.add_middleware(
            OPAAuthorizationMiddleware,
            config=OPAMiddlewareConfig(
                opa_url="http://opa:8181",
                policy_path="neuralhive/orchestrator/authz"
            )
        )
        ```
    """

    def __init__(
        self,
        app: ASGIApp,
        config: OPAMiddlewareConfig,
    ):
        """
        Inicializa middleware.

        Args:
            app: Aplicação ASGI
            config: Configuração do middleware
        """
        super().__init__(app)
        self.config = config

        # Configurar logger
        self._logger = logger.bind(component="opa_middleware")

        # Criar cliente OPA
        client_config = OPAClientConfig(
            opa_url=config.opa_url,
            default_timeout=config.timeout_seconds,
            enable_cache=config.enable_cache,
            cache_ttl_seconds=config.cache_ttl_seconds,
            fail_open=config.fail_open,
            circuit_breaker_enabled=config.circuit_breaker_enabled,
            circuit_breaker_failure_threshold=config.circuit_breaker_failure_threshold,
            circuit_breaker_reset_timeout=config.circuit_breaker_reset_timeout,
        )
        self._opa_client = OPAClient(
            opa_url=config.opa_url,
            policy_path=config.policy_path,
            config=client_config,
        )

        # Armazenar app para chamar_next
        self._app = app

        self._logger.info(
            "opa_middleware_initialized",
            opa_url=config.opa_url,
            policy_path=config.policy_path,
            fail_open=config.fail_open,
        )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """
        Processa requisição com verificação de autorização.

        Args:
            request: Requisição HTTP
            call_next: Próximo middleware/handler

        Returns:
            Response ou JSONResponse com erro de autorização
        """
        import time

        path = request.url.path
        method = request.method

        # Atualizar métrica de circuit breaker
        if self.config.metrics_enabled:
            cb_state = self._opa_client.get_circuit_breaker_state()
            opa_middleware_circuit_breaker_open.set(1 if cb_state == "OPEN" else 0)

        # 1. Verificar se path é público
        if self._is_public_path(path):
            self._logger.debug("public_path_allowed", path=path)
            return await call_next(request)

        # 2. Extrair headers de autenticação
        user_context = self._extract_user_context(request)

        # 3. Se não há contexto de usuário, retornar 403
        if not user_context["id"]:
            self._logger.warning("missing_auth_headers", path=path)
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "Forbidden",
                    "message": "Missing authentication headers",
                    "required_headers": [
                        self.config.user_id_header,
                        self.config.tenant_id_header,
                        self.config.role_header,
                    ],
                },
            )

        # 4. Construir input para OPA
        opa_input = await self._build_opa_input(request, user_context)

        # 5. Consultar OPA
        start_time = time.time()

        try:
            result = await self._opa_client.check(
                input_data=opa_input,
                policy_path=self.config.policy_path,
            )

            latency = time.time() - start_time
            if self.config.metrics_enabled:
                opa_middleware_latency_seconds.observe(latency)
                opa_middleware_decisions_total.labels(
                    decision="allow" if result.allow else "deny",
                    cached=str(result.cached).lower(),
                ).inc()

            if result.allow:
                # Autorizado - adicionar headers de auditoria e continuar
                self._logger.debug(
                    "access_allowed",
                    path=path,
                    method=method,
                    user_id=user_context["id"],
                    tenant_id=user_context["tenant_id"],
                    cached=result.cached,
                )
                return await call_next(request)
            else:
                # Negado
                self._logger.warning(
                    "access_denied",
                    path=path,
                    method=method,
                    user_id=user_context["id"],
                    tenant_id=user_context["tenant_id"],
                    reason=result.reason,
                )
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "error": "Forbidden",
                        "message": "Access denied by policy",
                        "reason": result.reason,
                    },
                )

        except Exception as e:
            latency = time.time() - start_time

            # Verificar se é erro de conexão (OPA indisponível)
            if "circuit" in str(e).lower() or "connection" in str(e).lower():
                if self.config.metrics_enabled:
                    opa_middleware_opa_unavailable_total.inc()

                self._logger.error(
                    "opa_unavailable",
                    path=path,
                    error=str(e),
                    fail_open=self.config.fail_open,
                )

                if self.config.fail_open:
                    # Fail-open - permitir acesso
                    return await call_next(request)
                else:
                    # Fail-closed - negar acesso com 503
                    return JSONResponse(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        content={
                            "error": "Service Unavailable",
                            "message": "Authorization service unavailable",
                        },
                    )
            else:
                # Outro erro - log e fail-closed por segurança
                self._logger.error(
                    "opa_error",
                    path=path,
                    error=str(e),
                    exc_info=True,
                )
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={
                        "error": "Service Unavailable",
                        "message": "Authorization error",
                    },
                )

    def _is_public_path(self, path: str) -> bool:
        """
        Verifica se path é público.

        Args:
            path: Caminho da requisição

        Returns:
            True se path é público
        """
        for public_path in self.config.public_paths:
            if path == public_path or path.startswith(public_path):
                return True
        return False

    def _extract_user_context(self, request: Request) -> dict[str, str]:
        """
        Extrai contexto de usuário dos headers.

        Args:
            request: Requisição HTTP

        Returns:
            Dicionário com id, tenant_id e role
        """
        return {
            "id": request.headers.get(self.config.user_id_header, ""),
            "tenant_id": request.headers.get(self.config.tenant_id_header, ""),
            "role": request.headers.get(self.config.role_header, ""),
        }

    async def _build_opa_input(
        self,
        request: Request,
        user_context: dict[str, str],
    ) -> dict[str, Any]:
        """
        Constrói input para consulta OPA.

        Args:
            request: Requisição HTTP
            user_context: Contexto do usuário extraído dos headers

        Returns:
            Input formatado para OPA
        """
        # Tentar ler body para POST/PUT requests (limitando tamanho)
        body_data = {}
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                # Limitar body a 10KB para não sobrecarregar
                body = await request.body()
                if body and len(body) <= 10240:
                    body_data = json.loads(body.decode())
            except (json.JSONDecodeError, Exception):
                body_data = {}

        return {
            "user": {
                "id": user_context["id"] or "anonymous",
                "tenant_id": user_context["tenant_id"] or "default",
                "role": user_context["role"] or "anonymous",
            },
            "request": {
                "method": request.method,
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "headers": dict(request.headers),
                "body": body_data,
            },
        }

    async def cleanup(self):
        """Limpa recursos do middleware."""
        await self._opa_client.close()

    def get_cache_stats(self) -> dict[str, int]:
        """Retorna estatísticas de cache."""
        return self._opa_client.get_cache_stats()

    def get_circuit_breaker_state(self) -> str:
        """Retorna estado do circuit breaker."""
        return self._opa_client.get_circuit_breaker_state()
