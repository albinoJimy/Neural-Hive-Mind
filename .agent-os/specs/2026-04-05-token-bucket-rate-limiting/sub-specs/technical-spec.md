# Technical Specification

Esta é a especificação técnica para a spec detalhada em @.agent-os/specs/2026-04-05-token-bucket-rate-limiting/spec.md

## Technical Requirements

### 1. Middleware FastAPI com Rate Limiting

**Arquivo:** `services/orchestrator-dynamic/src/middleware/rate_limit_middleware.py`

**Funcionalidades:**
- Extrair `tenant_id` e `user_id` do contexto de autenticação (JWT headers)
- Extrair `endpoint_path` da requisição (method + path)
- Construir chave Redis: `rate_limit:{tenant_id}:{user_id}:{endpoint_path}`
- Consultar/gerir bucket via TokenBucketRateLimiter
- Retornar HTTP 429 com header `Retry-After` se excedido
- Logs estruturados com contexto completo

**Assinatura:**
```python
class RateLimitMiddleware:
    def __init__(
        self,
        app: FastAPI,
        redis_client: Redis,
        limiter_factory: RateLimiterFactory,
        settings: OrchestratorSettings,
    )

    async def dispatch(self, request: Request, call_next: RequestResponseCycle) -> Response
```

### 2. Configurações Pydantic Settings

**Arquivo:** `services/orchestrator-dynamic/src/config/settings.py` (extensão)

**Novas configurações:**
```python
# Rate Limiting (Token Bucket)
enable_rate_limiting: bool = Field(default=True, description="Habilitar rate limiting")
rate_limit_redis_key_prefix: str = Field(default="rate_limit", description="Prefixo chaves Redis")
rate_limit_default_capacity: int = Field(default=100, description="Capacidade padrão tokens")
rate_limit_default_refill_rate: float = Field(default=10.0, description="Taxa reabastecimento padrão")
rate_limit_burst_multiplier: float = Field(default=2.0, description="Multiplicador burst capacity")
rate_limit_tier_limits: dict[str, dict] = Field(default_factory=dict, description="Limites por tier")
```

**Estrutura `rate_limit_tier_limits`:**
```python
{
    "premium": {"capacity": 1000, "refill_rate": 100.0},
    "basic": {"capacity": 100, "refill_rate": 10.0},
    "free": {"capacity": 10, "refill_rate": 1.0}
}
```

### 3. Integração Redis Distributed Backend

**Arquivo:** `services/orchestrator-dynamic/src/clients/rate_limit_redis.py`

**Funcionalidades:**
- Wrapper sobre Redis client existente
- Operações atômicas: get tokens, refill, decrement
- Lua script para evitar race conditions
- TTL automático para chaves não utilizadas

**Interface:**
```python
class RedisTokenBucketBackend:
    async def get_tokens(self, key: str) -> float
    async def refill_and_acquire(
        self, key: str, capacity: int, refill_rate: float, tokens: int
    ) -> RateLimitResult
    async def reset_key(self, key: str) -> None
```

**Lua Script (refill_and_acquire):**
```lua
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local tokens_requested = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local current = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(current[1]) or capacity
local last_refill = tonumber(current[2]) or now

-- Refill
local elapsed = now - last_refill
local new_tokens = math.min(capacity, tokens + (elapsed * refill_rate))

-- Acquire
local allowed = new_tokens >= tokens_requested
local remaining = 0
if allowed then
    remaining = new_tokens - tokens_requested
    redis.call('HMSET', key, 'tokens', remaining, 'last_refill', now)
else
    redis.call('HMSET', key, 'tokens', new_tokens, 'last_refill', now)
end

redis.call('EXPIRE', key, 3600)

return {allowed, remaining, (tokens_requested - new_tokens) / refill_rate}
```

### 4. Métricas Prometheus

**Arquivo:** `services/orchestrator-dynamic/src/metrics/rate_limit_metrics.py`

**Métricas expostas:**
```python
# Counter: Requisições processadas
rate_limit_requests_total = Counter(
    "rate_limit_requests_total",
    "Total rate limit checks",
    ["service", "tenant_id", "endpoint", "status"]  # status=allowed|denied
)

# Histogram: Tempo de espera por token
rate_limit_wait_duration_seconds = Histogram(
    "rate_limit_wait_duration_seconds",
    "Time waiting for rate limit token",
    ["service", "tenant_id"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

# Gauge: Tokens restantes
rate_limit_tokens_remaining = Gauge(
    "rate_limit_tokens_remaining",
    "Current tokens remaining in bucket",
    ["service", "tenant_id", "endpoint"]
)

# Counter: Throttle events por tenant
rate_limit_throttle_total = Counter(
    "rate_limit_throttle_total",
    "Total throttle events (429 responses)",
    ["service", "tenant_id", "tier"]
)
```

### 5. Configuração por Endpoint

**Arquivo:** `services/orchestrator-dynamic/src/config/rate_limit_config.py`

**Estrutura de configuração:**
```python
ENDPOINT_RATE_LIMITS: dict[str, RateLimitConfig] = {
    "POST:/api/v1/predict": RateLimitConfig(
        capacity=10,
        refill_rate=0.167,  # 10/min
        burst_multiplier=1.5,
    ),
    "POST:/api/v1/workflows": RateLimitConfig(
        capacity=50,
        refill_rate=0.833,  # 50/min
        burst_multiplier=2.0,
    ),
    "GET:/api/v1/health": RateLimitConfig(
        capacity=1000,
        refill_rate=16.67,  # 1000/min
        burst_multiplier=1.0,  # Sem burst
    ),
}
```

### 6. Integração no main.py

**Arquivo:** `services/orchestrator-dynamic/src/main.py`

**Modificações:**
```python
from src.middleware.rate_limit_middleware import RateLimitMiddleware
from src.clients.rate_limit_redis import RedisTokenBucketBackend
from src.metrics.rate_limit_metrics import init_rate_limit_metrics

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing code ...

    if settings.enable_rate_limiting:
        redis_backend = RedisTokenBucketBackend(redis_client)
        rate_limiter = RateLimitMiddleware(
            app=app,
            redis_client=redis_client,
            limiter_factory=RateLimiterFactory("orchestrator-dynamic"),
            settings=settings,
        )
        app.add_middleware(RateLimitMiddleware)

    yield
    # ... existing code ...
```

## API Changes

### Novos Headers de Resposta

**Header:** `RateLimit-Limit`
- Descrição: Limite configurado para a requisição
- Formato: `100;w=60` (100 requests por 60 segundos)
- Presente em: Todas as respostas

**Header:** `RateLimit-Remaining`
- Descrição: Tokens restantes no bucket
- Formato: Integer
- Presente em: Todas as respostas

**Header:** `RateLimit-Reset`
- Descrição: Timestamp Unix quando bucket será resetado
- Formato: Unix timestamp
- Presente em: Todas as respostas

**Header:** `Retry-After`
- Descrição: Segundos até próxima requisição permitida
- Formato: Integer (segundos)
- Presente em: Apenas respostas 429

### Exemplo de Resposta 429

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
RateLimit-Limit: 100;w=60
RateLimit-Remaining: 0
RateLimit-Reset: 1743849600
Retry-After: 45

{
    "error": "rate_limit_exceeded",
    "message": "Rate limit exceeded. Retry after 45 seconds.",
    "tenant_id": "tenant_123",
    "limit": 100,
    "window": 60,
    "retry_after": 45
}
```

## External Dependencies

**NESTE TICKET NÃO SÃO NECESSÁRIAS NOVAS DEPENDÊNCIAS**

- `neural_hive_resilience` já contém `TokenBucketRateLimiter`
- Redis client já está implementado em `src.clients.redis_client`
- Prometheus metrics já estão expostas via `prometheus_client`

**Versões mínimas requeridas:**
- `neural_hive_resilience >= 1.2.0` (já em uso)
- `redis >= 5.0.0` (já em uso)
- `prometheus-client >= 0.19.0` (já em uso)

## Performance Considerations

### Latência Adicional

- Target: < 5ms overhead por requisição (p99)
- Redis connection pooling: mínimo 10 conexões
- Pipeline de comandos Redis quando possível
- Cache local de configs (evitar parsing a cada request)

### Memory Footprint

- Chaves Redis com TTL de 1h (auto-expiration)
- ~100 bytes por chave (hash com tokens, last_refill)
- Para 10.000 usuários ativos: ~1MB Redis

### Burst Handling

- burst_multiplier permite consumir capacity * multiplier instantaneamente
- Útil para:
  - Retry storms (client-side retries)
  - Batch operations legítimas
  - Flash crowds

## Testing Strategy

### Unit Tests

**Arquivo:** `services/orchestrator-dynamic/tests/unit/test_rate_limit_middleware.py`

Casos de teste:
1. `test_middleware_allows_within_limit` - Requisição dentro do limite é permitida
2. `test_middleware_denies_exceeds_limit` - Requisição excedendo retorna 429
3. `test_middleware_different_users_separate_limits` - Usuários têm buckets independentes
4. `test_middleware_tier_override` - Tier premium respeita limites configurados
5. `test_middleware_endpoint_specific_limit` - Endpoint com limite específico
6. `test_middleware_headers_added` - Headers RateLimit-* presentes
7. `test_middleware_retry_after_calculated` - Retry-After calculado corretamente

### Integration Tests

**Arquivo:** `services/orchestrator-dynamic/tests/integration/test_rate_limit_redis_integration.py`

Casos de teste:
1. `test_redis_atomic_operations` - Lua script evita race condition
2. `test_redis_refill_across_requests` - Refill funciona cross-request
3. `test_redis_ttl_expiration` - Chaves não utilizadas expiram
4. `test_redis_concurrent_same_key` - Concorrência na mesma chave funciona

### E2E Tests

**Arquivo:** `services/orchestrator-dynamic/tests/e2e/test_rate_limit_e2e.py`

Casos de teste:
1. `test_e2e_tenant_rate_limit` - 1000 requests/min tenant premium funciona
2. `test_e2e_user_rate_limit` - Usuário individual respeita limite
3. `test_e2e_burst_behavior` - Burst de 2x capacity permitido
4. `test_e2e_metrics_exposed` - Métricas Prometheus visíveis
5. `test_e2e_throttle_recovery` - Após throttle, requests voltam a funcionar

## Configuration Examples

### .env Exemplo

```bash
# Rate Limiting
ENABLE_RATE_LIMITING=true
RATE_LIMIT_DEFAULT_CAPACITY=100
RATE_LIMIT_DEFAULT_REFILL_RATE=10.0
RATE_LIMIT_BURST_MULTIPLIER=2.0

# Tier limits (JSON)
RATE_LIMIT_TIER_LIMITS='{"premium":{"capacity":1000,"refill_rate":100.0},"basic":{"capacity":100,"refill_rate":10.0}}'
```

### Docker Compose Override

```yaml
services:
  orchestrator-dynamic:
    environment:
      - ENABLE_RATE_LIMITING=true
      - RATE_LIMIT_DEFAULT_CAPACITY=100
      - RATE_LIMIT_DEFAULT_REFILL_RATE=10.0
    volumes:
      - ./config/rate_limits.yaml:/app/config/rate_limits.yaml:ro
```

## Rollout Plan

### Phase 1: Feature Flag Disabled (Week 1)
- Implementar middleware
- Testes unitários e integração
- Deploy com `ENABLE_RATE_LIMITING=false`

### Phase 2: Shadow Mode (Week 2)
- Habilitar em shadow mode (log mas não bloquear)
- Coletar métricas baseline
- Validar que não há falso-positivos

### Phase 3: Gradual Rollout (Week 3-4)
- 10% do tráfego (whitelist tenants)
- 50% do tráfego
- 100% do tráfego

### Phase 4: Optimization (Week 5+)
- Ajustar limites baseado em métricas
- Adicionar endpoints específicos
- Otimizar performance se necessário
