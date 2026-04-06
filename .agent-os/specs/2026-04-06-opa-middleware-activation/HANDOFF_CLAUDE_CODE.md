# Handoff para Claude Code

> Spec: INFRA-005 - Middleware OPA Authorization Activation
> Status: Ready for Implementation
> Data: 2026-04-06

## Resumo

Ativar o `OPAAuthorizationMiddleware` da biblioteca `neural_hive_opa` no serviço `orchestrator-dynamic`, adicionando autorização centralizada via OPA para todas as requisições HTTP da API REST.

**Arquitetura:**
```
Request → CORS → OPA Authorization → RateLimit → API Handler
                     ↓
               allow/deny based on policy
```

## Arquivos a Modificar

### 1. `services/orchestrator-dynamic/src/config/settings.py`

Adicionar após as configurações OPA existentes:

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
    description="Se True, permite acesso quando OPA estiver indisponível"
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

### 2. `services/orchestrator-dynamic/src/main.py`

Adicionar middleware APÓS CORSMiddleware e ANTES de RateLimitMiddleware:

```python
# Após linha do CORSMiddleware (≈1061)

# OPA Authorization Middleware
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
            circuit_breaker_failure_threshold=config.opa_circuit_breaker_failure_threshold,
            circuit_breaker_reset_timeout_seconds=config.opa_circuit_breaker_reset_timeout_seconds,
        )
    )
```

### 3. `policies/rego/orchestrator/http_authz.rego` (NOVO)

Criar arquivo com a política de autorização HTTP (ver technical-spec.md)

## Testes

**Arquivo:** `services/orchestrator-dynamic/tests/integration/test_opa_middleware_integration.py`

Executar:
```bash
pytest tests/integration/test_opa_middleware_integration.py -v
```

## Deploy

1. Carregar política OPA:
```bash
opa policies import policies/rego/orchestrator/http_authz.rego
```

2. Deploy com feature flag:
```bash
ENABLE_OPA_AUTHORIZATION=true kubectl rollout restart deployment/orchestrator-dynamic
```

3. Validar:
```bash
# Sem auth deve retornar 403
curl -X GET http://orchestrator-dynamic/api/v1/workflows

# Com auth deve retornar 200/404
curl -X GET http://orchestrator-dynamic/api/v1/workflows \
  -H "X-User-ID: user-123" \
  -H "X-Tenant-ID: tenant-abc" \
  -H "X-User-Role: developer"
```

## Critérios de Sucesso

- [x] Paths públicos (/health, /metrics) funcionam sem auth
- [x] API sem headers retorna HTTP 403
- [x] API com headers válidos retorna HTTP 200/404 (não 403)
- [x] OPA indisponível retorna HTTP 503 (fail-closed)
- [x] Métricas Prometheus expostas
- [x] Tenant isolation funcionando

## Riscos

| Risco | Mitigação |
|-------|-----------|
| OPA down bloqueia tudo | Monitoramento + alerta; feature flag para desativar rápido |
| Latência adicionada | Cache de 5min já implementado |
| Headers não presentes | Documentar API; usar defaults para anonymous |

## Referências

- `libraries/python/neural_hive_opa/src/neural_hive_opa/middleware.py` - Middleware implementado
- `services/orchestrator-dynamic/src/main.py` - Linha ≈1055-1092
- `services/orchestrator-dynamic/src/config/settings.py` - Configurações
