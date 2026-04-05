# HANDOFF - Claude Code Implementation Guide

> Spec: Token Bucket Rate Limiting
> Data: 2026-04-05
> Status: Ready for Implementation

## Resumo Executivo

Implementar rate limiting hierárquico usando Token Bucket no Orchestrator Dynamic, substituindo dependência do OPA para throttling simples. Integra `neural_hive_resilience.TokenBucketRateLimiter` com Redis distribuído, middleware FastAPI e métricas Prometheus.

## Contexto Técnico

### Componentes Existente a Reutilizar

1. **neural_hive_resilience.TokenBucketRateLimiter**
   - Localização: `/home/jimy/NHM/Neural-Hive-Mind/libraries/python/neural_hive_resilience/neural_hive_resilience/rate_limiter.py`
   - Funcionalidade: Algoritmo Token Bucket completo com refill, acquire, reserve
   - **JÁ IMPLEMENTADO** - não precisa reescrever

2. **Redis Client**
   - Localização: `services/orchestrator-dynamic/src/clients/redis_client.py`
   - **JÁ IMPLEMENTADO** - reutilizar conexão existente

3. **Prometheus Metrics**
   - Localização: Já exposto via `prometheus_client` em `/metrics`
   - **ESTENDER** - adicionar novas métricas específicas

### Gap a Implementar

1. **Middleware FastAPI** - Nova implementação
2. **Redis Distributed Backend** - Nova implementação com Lua scripts
3. **Configurações Pydantic** - Extender `OrchestratorSettings`
4. **Métricas específicas** - Adicionar métricas rate limiting
5. **Config por endpoint** - Nova implementação

## Arquitetura da Solução

```
Request
   ↓
[RateLimitMiddleware]
   ↓ extrai contexto (tenant/user/endpoint)
   ↓
[RedisTokenBucketBackend]
   ↓ chave: rate_limit:{tenant}:{user}:{endpoint}
   ↓
[Lua Script] - refill_and_acquire
   ↓ (atômico)
Redis HMGET/HMSET
   ↓
RateLimitResult (allowed/denied)
   ↓
[Headers] RateLimit-*, Retry-After
   ↓
Response 200/429
```

## Arquivos a Criar/Modificar

### Novos Arquivos (Criar)

| Arquivo | Propósito | LOC Estimado |
|---------|-----------|--------------|
| `src/middleware/rate_limit_middleware.py` | Middleware FastAPI | ~150 LOC |
| `src/clients/rate_limit_redis.py` | Backend Redis distribuído | ~200 LOC |
| `src/metrics/rate_limit_metrics.py` | Métricas Prometheus | ~100 LOC |
| `src/config/rate_limit_config.py` | Config por endpoint | ~80 LOC |
| `tests/unit/test_rate_limit_middleware.py` | Unit tests middleware | ~200 LOC |
| `tests/integration/test_rate_limit_integration.py` | Integration tests | ~150 LOC |
| `tests/e2e/test_rate_limit_e2e.py` | E2E tests | ~180 LOC |
| `docs/RATE_LIMITING_DEPLOY.md` | Documentação deploy | ~100 LOC |

### Arquivos a Modificar (Estender)

| Arquivo | Modificação | Linhas |
|---------|-------------|--------|
| `src/config/settings.py` | Adicionar configs rate_limit | ~30 LOC |
| `src/main.py` | Integrar middleware no lifespan | ~20 LOC |

## Requisitos Não-Funcionais

### Performance
- Overhead máximo: 5ms (p99) por request
- Latência Redis (local cluster): < 2ms
- Lua script atômico para evitar race conditions

### Disponibilidade
- Redis com replicação (já existe)
- Feature flag para disable rápido
- Graceful degradation se Redis down

### Observabilidade
- Métricas Prometheus breakdown por tenant/endpoint
- Logs estruturados com contexto completo
- Traces OpenTelemetry (propagation existente)

## Sequência de Implementação Sugerida

### Fase 1: Foundation (Tasks 1-3)
1. Middleware base sem Redis (in-memory bucket)
2. Configurações Pydantic
3. Testes unitários middleware

### Fase 2: Distributed Backend (Tasks 2, 7)
1. Redis backend com Lua script
2. Integração middleware + Redis backend
3. Testes integração

### Fase 3: Observability (Tasks 4, 9)
1. Métricas Prometheus
2. Documentação deploy

### Fase 4: E2E & Polish (Tasks 5, 6, 8, 10)
1. Config por endpoint
2. Integração main.py
3. Testes E2E
4. Linting/formatação

## Scripts Úteis

### Executar Testes
```bash
# Unit tests
pytest services/orchestrator-dynamic/tests/unit/test_rate_limit_middleware.py -v

# Integration tests
pytest services/orchestrator-dynamic/tests/integration/test_rate_limit_integration.py -v

# E2E tests
pytest services/orchestrator-dynamic/tests/e2e/test_rate_limit_e2e.py -v

# Todos
pytest services/orchestrator-dynamic/tests/ -k rate_limit -v
```

### Verificar Métricas
```bash
# Local
curl http://localhost:9090/metrics | grep rate_limit

# Kubernetes
kubectl port-forward svc/orchestrator-dynamic 9090:9090
curl http://localhost:9090/metrics | grep rate_limit
```

### Linting/Formatação
```bash
# Lint
cd services/orchestrator-dynamic
ruff check src/middleware/rate_limit_middleware.py

# Format
black src/middleware/rate_limit_middleware.py

# Check all
ruff check .
black . --check
```

## Critérios de Aceite

- [ ] Requests dentro do limite retornam 200 com headers `RateLimit-*`
- [ ] Requests excedendo o limite retornam 429 com `Retry-After`
- [ ] Limites tenant/user/endpoint são independentes
- [ ] Bursts de até 2x capacity são permitidos
- [ ] Métricas Prometheus expostas em `/metrics`
- [ ] Testes E2E passando (incluindo concorrência)
- [ ] Documentação deploy completa
- [ ] Linting (ruff) sem erros
- [ ] Formatação (black) aplicada

## Dependências Externas

**NENHUMA NOVA DEPENDÊNCIA NECESSÁRIA**

Todas as bibliotecas já estão em uso:
- `neural_hive_resilience >= 1.2.0`
- `redis >= 5.0.0`
- `prometheus-client >= 0.19.0`
- `fastapi >= 0.100.0`

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Redis down | Baixa | Alto | Feature flag + circuit breaker |
| Race conditions | Média | Médio | Lua script atômico |
| Config complexa | Baixa | Baixo | Defaults sensatos |
| Performance regressão | Baixa | Alto | Benchmark + p99 monitoring |

## Próximos Passos

1. Revisar esta spec com o time
2. Criar branch `feat/TICKET-XXX-token-bucket-rate-limiting`
3. Executar tasks.md na ordem
4. Criar PR para review
5. Deploy com feature flag disabled (shadow mode)
6. Gradual rollout conforme métricas

## Referências

- Spec completa: `spec.md`
- Technical spec: `sub-specs/technical-spec.md`
- Tasks breakdown: `tasks.md`
- neural_hive_resilience: `/libraries/python/neural_hive_resilience/`
- Orchestrator settings: `services/orchestrator-dynamic/src/config/settings.py`

---

**Data de Criação:** 2026-04-05
**Autor:** Agent OS (Claude Code)
**Status:** Ready for Implementation
