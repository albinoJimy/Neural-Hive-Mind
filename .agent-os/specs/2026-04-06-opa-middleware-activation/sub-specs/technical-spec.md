# Technical Specification

## Middleware OPA Authorization Activation

### Requisitos Técnicos

#### 1. Modificações em `main.py`

**Ordem dos middlewares (CRITICAL):**
```python
# 1. CORS (sempre primeiro)
app.add_middleware(CORSMiddleware, ...)

# 2. OPA Authorization (NOVO - antes de RateLimit)
if config.enable_opa_authorization:
    from neural_hive_opa.middleware import OPAAuthorizationMiddleware, OPAMiddlewareConfig
    app.add_middleware(
        OPAAuthorizationMiddleware,
        config=OPAMiddlewareConfig(
            opa_url=f"http://{config.opa_host}:{config.opa_port}",
            policy_path=config.opa_authorization_policy_path,
            timeout_seconds=config.opa_timeout_seconds,
            cache_ttl_seconds=config.opa_cache_ttl_seconds,
            fail_open=config.opa_fail_open,
            user_id_header=config.opa_user_id_header,
            tenant_id_header=config.opa_tenant_id_header,
            role_header=config.opa_role_header,
            circuit_breaker_enabled=config.opa_circuit_breaker_enabled,
        )
    )

# 3. Rate Limit (após autorização)
if config.enable_rate_limiting:
    app.add_middleware(RateLimitMiddleware, ...)

# 4. Metrics
app.mount("/metrics", metrics_app)
```

#### 2. Configurações em `settings.py`

```python
# OPA Authorization Middleware (HTTP API)
enable_opa_authorization: bool = Field(
    default=True,
    description="Habilitar middleware de autorização OPA para API HTTP"
)
opa_authorization_policy_path: str = Field(
    default="neuralhive/orchestrator/authz",
    description="Path da política de autorização HTTP"
)
opa_fail_open: bool = Field(
    default=False,
    description="Se True, permite acesso quando OPA estiver indisponível (fail-open)"
)
opa_user_id_header: str = Field(
    default="X-User-ID",
    description="Header contendo o ID do usuário"
)
opa_tenant_id_header: str = Field(
    default="X-Tenant-ID",
    description="Header contendo o ID do tenant"
)
opa_role_header: str = Field(
    default="X-User-Role",
    description="Header contendo a role do usuário"
)
```

#### 3. Política OPA HTTP

**Arquivo:** `policies/rego/orchestrator/http_authz.rego`

```rego
package neuralhive.orchestrator.authz

import future.keywords.contains
import future.keywords.if
import future.keywords.in

default allow := false

# Endpoints públicos - sempre permitem
public_paths := [
    "/health",
    "/healthz",
    "/ready",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico"
]

allow if {
    input.request.path in public_paths
}

# Admins podem tudo
allow if {
    input.user.role == "admin"
}

# Developers podem fazer GET em APIs
allow if {
    input.user.role == "developer"
    input.request.method == "GET"
    startswith(input.request.path, "/api/")
}

# Tenants autenticados podem acessar recursos próprios
allow if {
    input.user.id != "anonymous"
    input.user.id != ""
    input.request.method in ["GET", "POST", "PUT", "DELETE"]
    startswith(input.request.path, "/api/v1/")
    # Valida tenant_id no path
    path_parts := split(input.request.path, "/")
    path_parts[4] == input.user.tenant_id
}

# Workers (service accounts) podem acessar /api/v1/workers/*
allow if {
    input.user.role == "worker"
    input.request.method in ["GET", "POST"]
    startswith(input.request.path, "/api/v1/workers/")
}

# Service Registry pode registrar/desregistrar
allow if {
    input.user.role == "service-registry"
    input.request.method in ["POST", "DELETE"]
    input.request.path == "/api/v1/workers/register"
}
```

#### 4. Testes de Integração

**Arquivo:** `tests/integration/test_opa_middleware_integration.py`

```python
import pytest
from httpx import AsyncClient
from fastapi import FastAPI

from neural_hive_opa.middleware import OPAAuthorizationMiddleware, OPAMiddlewareConfig


@pytest.mark.asyncio
class TestOPAMiddlewareIntegration:
    """Testes de integração do OPAAuthorizationMiddleware."""

    async def test_public_path_without_auth(self, client: AsyncClient):
        """Paths públicos não requerem autenticação."""
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_api_without_auth_returns_403(self, client: AsyncClient):
        """API sem header de autenticação retorna 403."""
        response = await client.get("/api/v1/workflows")
        assert response.status_code == 403

    async def test_api_with_valid_auth_returns_200(self, client: AsyncClient):
        """API com headers válidos retorna 200."""
        headers = {
            "X-User-ID": "user-123",
            "X-Tenant-ID": "tenant-abc",
            "X-User-Role": "developer"
        }
        response = await client.get("/api/v1/workflows", headers=headers)
        assert response.status_code in [200, 404]  # 404 se vazio, 200 se tiver dados

    async def test_admin_can_access_everything(self, client: AsyncClient):
        """Admin role tem acesso irrestrito."""
        headers = {
            "X-User-ID": "admin-1",
            "X-Tenant-ID": "system",
            "X-User-Role": "admin"
        }
        response = await client.post("/api/v1/workflows/start", json={}, headers=headers)
        # Pode retornar 422 (validation) mas não 403 (authz)
        assert response.status_code != 403

    async def test_tenant_isolation(self, client: AsyncClient):
        """Tenant A não pode acessar recursos do Tenant B."""
        headers_a = {
            "X-User-ID": "user-a",
            "X-Tenant-ID": "tenant-a",
            "X-User-Role": "developer"
        }
        headers_b = {
            "X-User-ID": "user-b",
            "X-Tenant-ID": "tenant-b",
            "X-User-Role": "developer"
        }
        # Request para recurso do tenant-b com headers do tenant-a
        response = await client.get("/api/v1/workflows/tenant-b/workflow-123", headers=headers_a)
        assert response.status_code == 403

    async def test_cache_hit_reduces_latency(self, client: AsyncClient):
        """Segunda request com mesmo input usa cache."""
        headers = {
            "X-User-ID": "user-123",
            "X-Tenant-ID": "tenant-abc",
            "X-User-Role": "developer"
        }
        # Primeira request (cache miss)
        await client.get("/api/v1/workflows", headers=headers)
        # Segunda request (cache hit)
        await client.get("/api/v1/workflows", headers=headers)
        # Validar métrica de cache hit incrementou

    async def test_opa_unavailable_returns_503(self, client_with_opa_down: AsyncClient):
        """Quando OPA está down, retorna 503 (fail-closed)."""
        headers = {
            "X-User-ID": "user-123",
            "X-Tenant-ID": "tenant-abc",
            "X-User-Role": "developer"
        }
        response = await client.get("/api/v1/workflows", headers=headers)
        assert response.status_code == 503
```

#### 5. Métricas Prometheus

```python
# Métricas expostas pelo middleware:
- opa_middleware_decisions_total{decision="allow|deny"} - Counter
- opa_middleware_latency_seconds{quantile="0.5|0.9|0.99"} - Histogram
- opa_middleware_cache_hits_total - Counter
- opa_middleware_cache_misses_total - Counter
- opa_middleware_circuit_breaker_open - Gauge
- opa_middleware_opa_unavailable_total - Counter
```

### Dependências Externas

**Nova dependência (já indiretamente incluída):**
- `neural_hive_opa` - Já em `libraries/python/neural_hive_opa/`

### Configuração OPA

**Política deve ser carregada no OPA:**
```bash
# Carregar política
opa policies import \
  --bundle neuralhive/orchestrator \
  policies/rego/orchestrator/http_authz.rego
```
