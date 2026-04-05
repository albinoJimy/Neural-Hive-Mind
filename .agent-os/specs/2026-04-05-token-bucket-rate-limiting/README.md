# Token Bucket Rate Limiting - Spec Summary

> **Status:** Ready for Implementation
> **Data:** 2026-04-05
> **Prioridade:** Alta

## Visão Geral

Implementar rate limiting hierárquico usando algoritmo Token Bucket no Orchestrator Dynamic para substituir a dependência do OPA em cenários simples de throttling.

## Objetivos

1. **Proteção contra Sobrecarga** - Limitar requisições por tenant para evitar que um afete outros
2. **Controle Granular** - Limites por tenant > user > endpoint
3. **Observabilidade** - Métricas Prometheus detalhadas
4. **Burst Control** - Permitir bursts temporários para picos legítimos

## Arquitetura

```
Request → RateLimitMiddleware → Redis (Token Bucket) → Response 200/429
                  ↓
            Extract Context
         (tenant/user/endpoint)
                  ↓
            Lookup Config
          (tier/endpoint limits)
                  ↓
            Lua Script (Atômico)
         refill_and_acquire
                  ↓
         Update Metrics (Prometheus)
```

## Componentes

| Componente | Descrição | Status |
|------------|-----------|--------|
| `TokenBucketRateLimiter` | Algoritmo existente em `neural_hive_resilience` | ✅ Pronto |
| `RateLimitMiddleware` | Middleware FastAPI (NOVO) | ⏳ Implementar |
| `RedisTokenBucketBackend` | Backend distribuído com Lua (NOVO) | ⏳ Implementar |
| `RateLimitConfig` | Config por endpoint (NOVO) | ⏳ Implementar |
| Métricas Prometheus | Métricas rate_limit_* (NOVO) | ⏳ Implementar |

## Arquivos da Spec

```
.agent-os/specs/2026-04-05-token-bucket-rate-limiting/
├── README.md                 (este arquivo)
├── spec.md                   Spec completa (overview, user stories, scope)
├── spec-lite.md              Resumo executivo
├── tasks.md                  Decomposição em 10 tasks principais
├── HANDOFF_CLAUDE_CODE.md    Guide para implementação
├── architecture.md           Diagramas e arquitetura detalhada
├── config-examples.yaml      Exemplos de configuração
└── sub-specs/
    └── technical-spec.md     Especificação técnica completa
```

## Resumo dos Tasks

1. **Middleware Base** - Criar `RateLimitMiddleware` com extração de contexto
2. **Redis Backend** - Implementar `RedisTokenBucketBackend` com Lua script
3. **Configurações** - Estender `OrchestratorSettings` com configs rate_limit
4. **Métricas** - Adicionar métricas Prometheus (Counter, Histogram, Gauge)
5. **Endpoint Config** - Configuração granular por endpoint
6. **Integração** - Integrar middleware no `main.py`
7. **Integration Tests** - Testes de integração Redis
8. **E2E Tests** - Testes end-to-end com Docker Compose
9. **Documentação** - Guia de deploy e troubleshooting
10. **Qualidade** - Linting, formatação, cobertura testes

## Deliverables Esperados

- [ ] Requests limitadas retornam HTTP 429 com `Retry-After`
- [ ] Hierarquia tenant > user > endpoint respeitada
- [ ] Bursts de até 2x capacity permitidos
- [ ] Métricas Prometheus expostas em `/metrics`
- [ ] Testes E2E passando
- [ ] Documentação deploy completa

## Configuração Exemplo

```bash
# .env
ENABLE_RATE_LIMITING=true
RATE_LIMIT_DEFAULT_CAPACITY=100
RATE_LIMIT_DEFAULT_REFILL_RATE=10.0
RATE_LIMIT_BURST_MULTIPLIER=2.0
```

```python
# tier limits (JSON)
{
  "premium": {"capacity": 1000, "refill_rate": 100.0},
  "basic": {"capacity": 100, "refill_rate": 10.0},
  "free": {"capacity": 10, "refill_rate": 1.0}
}
```

## Métricas Prometheus

```promql
# Taxa de throttle por tenant
rate(rate_limit_requests_total{status="denied"}[5m]) by (tenant_id)

# Tokens restantes
rate_limit_tokens_remaining{tenant_id="tenant_123"}

# Tempo de espera p99
histogram_quantile(0.99, rate_limit_wait_duration_seconds)
```

## Próximos Passos

1. Revisar esta spec com o time
2. Criar branch `feat/TICKET-XXX-token-bucket-rate-limiting`
3. Executar `tasks.md` sequencialmente
4. Criar PR para review
5. Deploy com feature flag disabled (shadow mode)
6. Gradual rollout

## Documentos Relacionados

- `spec.md` - Spec completa com user stories e scope
- `technical-spec.md` - Detalhes técnicos de cada componente
- `architecture.md` - Diagramas de sequência e arquitetura
- `HANDOFF_CLAUDE_CODE.md` - Guide para Claude Code implementar
- `config-examples.yaml` - Exemplos práticos de configuração

## Referências

- `neural_hive_resilience` - `/libraries/python/neural_hive_resilience/neural_hive_resilience/rate_limiter.py`
- Orchestrator Settings - `/services/orchestrator-dynamic/src/config/settings.py`
- Redis Client - `/services/orchestrator-dynamic/src/clients/redis_client.py`
