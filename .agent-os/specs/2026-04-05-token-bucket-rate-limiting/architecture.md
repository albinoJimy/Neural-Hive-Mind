# Arquitetura - Token Bucket Rate Limiting

## Diagrama de Sequência

```
┌─────────┐                ┌─────────────┐          ┌──────────┐
│  Client │                │  FastAPI    │          │  Redis   │
└────┬────┘                └──────┬──────┘          └────┬─────┘
     │                            │                      │
     │  POST /api/v1/workflows    │                      │
     │  (JWT: tenant, user)       │                      │
     ├───────────────────────────>│                      │
     │                            │                      │
     │                    ┌───────▼───────┐             │
     │                    │ RateLimit     │             │
     │                    │ Middleware    │             │
     │                    └───────┬───────┘             │
     │                            │                      │
     │                            │ 1. Extract Context  │
     │                            │ tenant_id, user_id  │
     │                            │ endpoint_path       │
     │                            │                      │
     │                            │ 2. Build Redis Key  │
     │                            │ "rate_limit:123:456 │
     │                            │ :POST:/workflows"   │
     │                            │                      │
     │                            │ 3. Lua Script       │
     │                            │ refill_and_acquire() │
     │                            ├─────────────────────>│
     │                            │                      │
     │                            │                      │ HMGET
     │                            │                      │ tokens, last_refill
     │                            │<─────────────────────┤
     │                            │                      │
     │                            │                      │ Calculate refill
     │                            │                      │
     │                            │                      │ HMSET new state
     │                            │<─────────────────────┤
     │                            │                      │
     │                            │ 4. RateLimitResult   │
     │                            │ allowed=true/false   │
     │                            │                      │
     │                            │ 5. Update Metrics    │
     │                            │ Prometheus           │
     │                            │                      │
     │  200 OK                    │                      │
     │  RateLimit-* headers       │                      │
     │<───────────────────────────│                      │
     │                            │                      │
     │  OU                        │                      │
     │                            │                      │
     │  429 Too Many Requests     │                      │
     │  Retry-After header        │                      │
     │<───────────────────────────│                      │
```

## Hierarquia de Chaves Redis

```
rate_limit:{tenant_id}:{user_id}:{endpoint_path}

Exemplos:
├── rate_limit:tenant_premium:user_alice:POST:/api/v1/predict
│   └── capacity: 10, refill: 0.167 tokens/s
├── rate_limit:tenant_premium:user_alice:POST:/api/v1/workflows
│   └── capacity: 50, refill: 0.833 tokens/s
├── rate_limit:tenant_basic:user_bob:POST:/api/v1/workflows
│   └── capacity: 20, refill: 0.333 tokens/s
└── rate_limit:tenant_free:user_charlie:GET:/api/v1/health
    └── capacity: 10000, refill: 166.67 tokens/s
```

## Token Bucket Algorithm

```
┌─────────────────────────────────────────┐
│         TOKEN BUCKET (capacity=N)       │
│                                         │
│  ┌───┬───┬───┬───┬───┬───┬───┬───┬───┐ │
│  │ T │ T │ T │ T │ T │ T │   │   │   │ │  ← Tokens
│  └───┴───┴───┴───┴───┴───┴───┴───┴───┘ │
│    ╵   ╵   ╵   ╵   ╵   ╵               │
│    └───┴───┴───┴───┴───┘               │
│         Refill Rate (R tokens/s)        │
│                                         │
└─────────────────────────────────────────┘

Comportamento:
- Tokens reabastecem a R tokens/segundo
- Capacidade máxima = N tokens
- Burst: até N tokens podem ser consumidos instantaneamente
- Após burst, deve esperar reabastecimento

Exemplo (capacity=100, refill=10/s):
├── t=0s:    100 tokens (cheio)
├── t=1s:    consumo de 50 tokens → 50 restantes
├── t=2s:    reabastecimento de 10 → 60 restantes
├── t=5s:    10x10 = 100 tokens (cheio novamente)
└── t=10s:   burst de 200 tokens? NÃO! Máximo=100
```

## Fluxo de Decisão

```
                 Request Chegou
                      │
                      ▼
            ┌─────────────────┐
            │ Feature Flag    │──── NO ────→ Pass Through
            │ Enabled?        │                (sem rate limiting)
            └────────┬────────┘
                     │ YES
                     ▼
        ┌────────────────────────┐
        │ Extrair Contexto       │
        │ (tenant, user, endpoint)│
        └────────────┬───────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │ Lookup Config          │
        │ (tier, endpoint)       │
        └────────────┬───────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │ Gerar Chave Redis       │
        │ rate_limit:{t}:{u}:{e}  │
        └────────────┬───────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │ Lua Script (Atômico)   │
        │ 1. HMGET estado        │
        │ 2. Calcular refill     │
        │ 3. Tentar acquire      │
        │ 4. HMSET novo estado   │
        └────────────┬───────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
      Allowed                  Denied
         │                       │
         ▼                       ▼
  ┌──────────────┐      ┌──────────────┐
  │ Atualizar    │      │ Atualizar    │
  │ Métricas     │      │ Métricas     │
  │ (allowed)    │      │ (denied)     │
  └──────┬───────┘      └──────┬───────┘
         │                       │
         ▼                       ▼
  ┌──────────────┐      ┌──────────────┐
  │ Add Headers  │      │ HTTP 429     │
  │ RateLimit-*  │      │ Retry-After  │
  └──────┬───────┘      └──────┬───────┘
         │                       │
         ▼                       │
  ┌──────────────┐               │
  │ 200 OK       │               │
  └──────┬───────┘               │
         │                       │
         └───────────┬───────────┘
                     ▼
            Return Response
```

## Métricas Prometheus

```
rate_limit_requests_total
├── labels: service, tenant_id, endpoint, status
├── type: Counter
└── queries:
    ├── rate(requests{status="allowed"}[5m])
    └── rate(requests{status="denied"}[5m])

rate_limit_wait_duration_seconds
├── labels: service, tenant_id
├── type: Histogram
│   ├── buckets: 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0
└── queries:
    ├── histogram_quantile(0.99, wait_duration)
    └── rate(wait_duration_sum[5m]) / rate(wait_duration_count[5m])

rate_limit_tokens_remaining
├── labels: service, tenant_id, endpoint
├── type: Gauge
└── queries:
    └── tokens_remaining{tenant_id="tenant_123"}

rate_limit_throttle_total
├── labels: service, tenant_id, tier
├── type: Counter
└── queries:
    └── rate(throttle_total[5m]) by (tier)
```

## Integração com neural_hive_resilience

```
neural_hive_resilience.rate_limiter
│
├── TokenBucketRateLimiter (EXISTE)
│   ├── __init__(capacity, refill_rate, service_name, limiter_name)
│   ├── async acquire(tokens, block, timeout) → RateLimitResult
│   └── async reserve(tokens) → float
│
└── RateLimitResult (EXISTE)
    ├── allowed: bool
    ├── tokens_remaining: int
    ├── retry_after: float
    └── reset_time: float

NOVO: RedisTokenBucketBackend
├── __init__(redis_client)
├── async get_tokens(key) → float
├── async refill_and_acquire(key, capacity, refill_rate, tokens) → RateLimitResult
└── async reset_key(key) → None

NOVO: RateLimitMiddleware (FastAPI)
├── __init__(app, redis_client, limiter_factory, settings)
├── async dispatch(request, call_next) → Response
└── _extract_context(request) → tuple[tenant_id, user_id, endpoint]
```

## Configuração em Camadas

```
Priority (maior primeiro):
1. Endpoint-specific (ENDPOINT_RATE_LIMITS)
2. Tier-specific (RATE_LIMIT_TIER_LIMITS)
3. Default (RATE_LIMIT_DEFAULT_*)

Exemplo de lookup:
POST /api/v1/predict
└── tenant=premium, user=alice
    1. ENDPOINT_RATE_LIMITS["POST:/api/v1/predict"]
       └── capacity=10, refill=0.167 ✓ (ENCONTRADO)

POST /api/v1/unknown
└── tenant=premium, user=alice
    1. ENDPOINT_RATE_LIMITS["POST:/api/v1/unknown"]
       └── NÃO ENCONTRADO
    2. RATE_LIMIT_TIER_LIMITS["premium"]
       └── capacity=1000, refill=100.0 ✓ (ENCONTRADO)

GET /api/v1/health
└── tenant=unknown, user=bob
    1. ENDPOINT_RATE_LIMITS["GET:/api/v1/health"]
       └── capacity=10000, refill=166.67 ✓ (ENCONTRADO)
```

## Estados do Bucket em Redis

```
Hash: rate_limit:tenant_123:user_456:POST:/api/v1/workflows

Fields:
├── tokens: 75.5          (float, tokens disponíveis)
├── last_refill: 1743840000.123 (float, timestamp Unix)
└── TTL: 3600             (auto-expiration)

Transição:
┌─────────────────────────────────────────┐
│  Estado: tokens=50, last_refill=t0      │
├─────────────────────────────────────────┤
│  Request chega (1 token)                │
│  → Elapsed = now - t0 = 2 segundos      │
│  → Refill = 2 * 10.0 = 20 tokens        │
│  → New tokens = min(100, 50+20) = 70    │
│  → After consume = 70 - 1 = 69          │
│  → Estado: tokens=69, last_refill=now   │
└─────────────────────────────────────────┘
```

## Diagrama de Deploy

```
┌─────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                   │
│                                                          │
│  ┌───────────────────────────────────────────────────┐ │
│  │             Orchestrator Dynamic (Pod)            │ │
│  │                                                   │ │
│  │  ┌─────────────┐      ┌─────────────┐            │ │
│  │  │  FastAPI    │────>│  RateLimit  │            │ │
│  │  │             │      │  Middleware │            │ │
│  │  └─────────────┘      └──────┬──────┘            │ │
│  │                              │                    │ │
│  │                              │ Redis TCP          │ │
│  │                              ▼                    │ │
│  │  ┌─────────────┐      ┌─────────────┐            │ │
│  │  │ Prometheus  │<────│  Metrics    │            │ │
│  │  │  /metrics   │      │  Exporter  │            │ │
│  │  └─────────────┘      └─────────────┘            │ │
│  └───────────────────────────────────────────────────┘ │
│                         │                               │
│                         │ Redis TCP                     │
│                         ▼                               │
│  ┌───────────────────────────────────────────────────┐ │
│  │              Redis Cluster (HA)                    │ │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐           │ │
│  │  │ Master  │──│ Replica │──│ Replica │           │ │
│  │  └─────────┘  └─────────┘  └─────────┘           │ │
│  │                                                     │ │
│  │  Keys:                                             │ │
│  │  - rate_limit:* (TTL 1h)                           │ │
│  │  - ~100 bytes/key                                  │ │
│  │  - ~10k users = ~1MB                               │ │
│  └───────────────────────────────────────────────────┘ │
│                                                          │
│  ┌───────────────────────────────────────────────────┐ │
│  │                 Prometheus                         │ │
│  │  Scrape: /metrics (15s interval)                  │ │
│  │  Alerts: High throttle rate                       │ │
│  └───────────────────────────────────────────────────┘ │
│                                                          │
│  ┌───────────────────────────────────────────────────┐ │
│  │                 Grafana                            │ │
│  │  Dashboard: Rate Limiting Overview                │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Tratamento de Erros

```
┌─────────────────────────────────────────────┐
│         Error Handling Strategy             │
├─────────────────────────────────────────────┤
│                                             │
│  Redis Down:                                │
│  ├── Circuit Breaker abre após N falhas    │
│  ├── Feature flag permite disable rápido   │
│  └── Fallback: Pass-through (log warning)  │
│                                             │
│  Lua Script Error:                          │
│  ├── Log error com contexto                 │
│  ├── Métrica: rate_limit_errors increment  │
│  └── Fallback: Allow (fail-open)           │
│                                             │
│  Invalid Context (no tenant/user):          │
│  ├── Usar "anonymous" como tenant          │
│  ├── Aplicar limites estritos (free tier)  │
│  └── Log warning para debugging            │
│                                             │
│  Configuration Error:                       │
│  ├── Validar no startup (Pydantic)         │
│  ├── Recusar iniciar se config inválida    │
│  └── Alert operador via health check       │
│                                             │
└─────────────────────────────────────────────┘
```

## Timeline de Implementação

```
Week 1: Foundation
├── Middleware base (in-memory)
├── Configurações Pydantic
└── Unit tests

Week 2: Distributed Backend
├── Redis backend + Lua script
├── Integração middleware
└── Integration tests

Week 3: Observability
├── Métricas Prometheus
├── Documentação
└── Dashboard templates

Week 4: E2E & Polish
├── Config por endpoint
├── E2E tests
├── Linting/formatação
└── Code review

Week 5+: Gradual Rollout
├── Feature flag disabled (shadow mode)
├── 10% traffic (whitelist)
├── 50% traffic
├── 100% traffic
└── Monitoramento contínuo
```
