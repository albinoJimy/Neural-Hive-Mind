# Neural Hive OPA

Biblioteca de integração com Open Policy Agent (OPA) para serviços Neural Hive Mind.

## Funcionalidades

- **Cliente OPA** com retry automático e circuit breaker
- **Middleware FastAPI** para autorização HTTP centralizada
- **Cache de decisões** para reduzir latência
- **Métricas Prometheus** para observabilidade
- **Suporte a fail-open/fail-closed** para alta disponibilidade

## Instalação

```bash
pip install neural-hive-opa
```

## Uso

### Middleware FastAPI

```python
from fastapi import FastAPI
from neural_hive_opa import OPAAuthorizationMiddleware, OPAMiddlewareConfig

app = FastAPI()

app.add_middleware(
    OPAAuthorizationMiddleware,
    config=OPAMiddlewareConfig(
        opa_url="http://opa:8181",
        policy_path="neuralhive/orchestrator/authz",
        fail_open=False,  # Fail-closed por padrão
    )
)
```

### Cliente OPA Direto

```python
from neural_hive_opa import OPAClient, OPARequestOptions

client = OPAClient(
    opa_url="http://opa:8181",
    policy_path="neuralhive/orchestrator/authz"
)

result = await client.check(
    input_data={
        "user": {"id": "123", "role": "admin"},
        "request": {"method": "GET", "path": "/api/v1/workflows"}
    }
)

if result.allow:
    print("Acesso permitido")
else:
    print(f"Acesso negado: {result.reason}")
```

## Headers de Autenticação

O middleware espera os seguintes headers nas requisições:

- `X-User-ID`: ID do usuário
- `X-Tenant-ID`: ID do tenant
- `X-User-Role`: Role do usuário (admin, developer, worker, etc.)

## Métricas Prometheus

- `opa_requests_total`: Requisições ao OPA
- `opa_latency_seconds`: Latência das requisições
- `opa_cache_hits_total`: Cache hits
- `opa_middleware_decisions_total`: Decisões do middleware
- `opa_middleware_circuit_breaker_open`: Estado do circuit breaker

## Licença

MIT
