# Rate Limiting Deploy Guide

Guia de deploy e configuracao do Token Bucket Rate Limiting no Orchestrator Dynamic.

## Visao Geral

O Token Bucket Rate Limiting e um mecanismo de controle de fluxo hierarquico que protege o Orchestrator Dynamic contra sobrecarga, permitindo configuracao granular por tenant, usuario e endpoint.

### Caracteristicas Principais

- **Algoritmo Token Bucket**: Permite bursts temporarios acima da taxa base
- **Hierarquia de Limites**: tenant > usuario > endpoint
- **Backend Redis Distribuido**: Operacoes atomicas via Lua script
- **Fail-Open**: Permite requisicoes se Redis estiver indisponivel
- **Metricas Prometheus Integradas**: Monitoramento em tempo real

### Fluxo da Requisicao

```
Request -> RateLimitMiddleware -> Extract Context (tenant/user/endpoint)
  -> Build Redis Key -> Lua Script (atomic) -> Allow/Deny -> Response
```

## Variaveis de Ambiente

### Feature Flag

| Variavel | Default | Descricao |
|----------|---------|-----------|
| `ENABLE_RATE_LIMITING` | `false` | Habilita/desabilita rate limiting globalmente |

### Configuracoes Padrao

| Variavel | Default | Descricao |
|----------|---------|-----------|
| `RATE_LIMIT_DEFAULT_CAPACITY` | `100` | Capacidade base do bucket (maximo de tokens) |
| `RATE_LIMIT_DEFAULT_REFILL_RATE` | `10.0` | Taxa de reabastecimento (tokens por segundo) |
| `RATE_LIMIT_BURST_MULTIPLIER` | `2.0` | Multiplicador para bursts (1.0 a 5.0) |
| `RATE_LIMIT_REDIS_KEY_PREFIX` | `rate_limit` | Prefixo para chaves Redis |

### Configuracao por Tier (JSON)

| Variavel | Default | Descricao |
|----------|---------|-----------|
| `RATE_LIMIT_TIER_LIMITS` | (ver abaixo) | Limites especificos por tier de cliente |

## Configuracao por Tier

### Formato JSON

```json
{
  "premium": {
    "capacity": 1000,
    "refill_rate": 50.0,
    "burst_multiplier": 2.0
  },
  "standard": {
    "capacity": 500,
    "refill_rate": 25.0,
    "burst_multiplier": 2.0
  },
  "basic": {
    "capacity": 100,
    "refill_rate": 10.0,
    "burst_multiplier": 1.5
  }
}
```

### Exemplos de Configuracao

#### Tier Premium (Alta Demanda)

```bash
# docker-compose.yml ou Kubernetes ConfigMap
RATE_LIMIT_TIER_LIMITS='{"premium":{"capacity":1000,"refill_rate":50.0,"burst_multiplier":2.0}}'
```

- **Capacidade**: 1000 tokens
- **Refill**: 50 tokens/segundo
- **Burst Max**: 2000 tokens
- **Use Case**: Clientes corporativos com alto volume

#### Tier Standard

```bash
RATE_LIMIT_TIER_LIMITS='{"standard":{"capacity":500,"refill_rate":25.0,"burst_multiplier":2.0}}'
```

- **Capacidade**: 500 tokens
- **Refill**: 25 tokens/segundo
- **Burst Max**: 1000 tokens
- **Use Case**: Clientes regulares

#### Tier Basic (Baixa Demanda)

```bash
RATE_LIMIT_TIER_LIMITS='{"basic":{"capacity":100,"refill_rate":10.0,"burst_multiplier":1.5}}'
```

- **Capacidade**: 100 tokens
- **Refill**: 10 tokens/segundo
- **Burst Max**: 150 tokens
- **Use Case**: Clientes free/desenvolvedores

## Configuracao por Endpoint

Endpoints podem ter limites especificos definidos em `src/config/rate_limit_config.py`:

| Endpoint | Capacidade | Refill Rate | Descricao |
|----------|-----------|-------------|-----------|
| `POST:/api/v1/workflows` | 50 | 5/sec | Criacao de workflows |
| `POST:/api/v1/predict` | 10 | 1/sec | Predictions ML (custoso) |
| `GET:/api/v1/health` | 1000 | 100/sec | Health checks (barato) |

### Adicionar Novo Endpoint

Edite `src/config/rate_limit_config.py`:

```python
ENDPOINT_RATE_LIMITS: dict[str, RateLimitConfig] = {
    # ... existentes ...
    "POST:/api/v1/custom-endpoint": RateLimitConfig(
        capacity=200,
        refill_rate=20,
        burst_multiplier=2.0,
    ),
}
```

## Estrategia de Deploy

### Fase 1: Feature Flag Off (Testes Internos)

```yaml
# .env.test
ENABLE_RATE_LIMITING=false
```

- Deploy sem rate limiting ativo
- Verificar que o sistema funciona normalmente
- Metricas sao coletadas mas sem bloqueio

### Fase 2: Whitelist (Deploy Parcial)

```yaml
# .env.staging
ENABLE_RATE_LIMITING=true
RATE_LIMIT_TIER_LIMITS='{"whitelist":{"capacity":10000,"refill_rate":1000.0}}'
```

- Habilitar para tenants especificos (whitelist)
- Monitorar metricas e logs
- Ajustar limites conforme necessario

### Fase 3: Full Rollout (Producao)

```yaml
# .env.production
ENABLE_RATE_LIMITING=true
RATE_LIMIT_TIER_LIMITS='{"premium":...,"standard":...,"basic":...}'
```

- Ativar para todos os tenants
- Monitorar alertas Prometheus
- Ter plano de rollback pronto

## Headers HTTP

### Headers de Requisicao (Obrigatorios)

| Header | Descricao | Exemplo |
|--------|-----------|---------|
| `X-Tenant-ID` | Identificador do tenant | `tenant-123` |
| `X-User-ID` | Identificador do usuario | `user-456` |

### Headers de Resposta

| Header | Descricao | Exemplo |
|--------|-----------|---------|
| `RateLimit-Limit` | Limite configurado | `100;w=60` |
| `RateLimit-Remaining` | Tokens restantes | `42` |
| `RateLimit-Reset` | Timestamp de reset | `1712354400` |
| `Retry-After` | Segundos para retry (429) | `60` |

## Metricas Prometheus

### Metricas Disponiveis

#### Counter: `rate_limit_requests_total`

Total de requisicoes processadas pelo rate limiter.

**Labels:**
- `service`: Nome do servico (ex: `orchestrator-dynamic`)
- `tenant_id`: ID do tenant
- `endpoint`: Path do endpoint
- `status`: `allowed` ou `throttled`

#### Histogram: `rate_limit_wait_duration_seconds`

Tempo de espera para aquisicao de tokens.

**Labels:**
- `service`: Nome do servico
- `tenant_id`: ID do tenant

**Buckets:** `[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]`

#### Gauge: `rate_limit_tokens_remaining`

Tokens restantes no bucket.

**Labels:**
- `service`: Nome do servico
- `tenant_id`: ID do tenant
- `user_id`: ID do usuario
- `endpoint`: Path do endpoint

#### Counter: `rate_limit_throttle_total`

Total de requisicoes throttled.

**Labels:**
- `service`: Nome do servico
- `tenant_id`: ID do tenant
- `reason`: `capacity_exceeded`, `tier_limit`, `burst_exceeded`

#### Counter: `rate_limit_redis_errors_total`

Total de erros Redis no rate limiting.

**Labels:**
- `service`: Nome do servico
- `operation`: `acquire`, `get_tokens`, `reset`, `delete`

## Queries Prometheus Exemplo

### Taxa de Requisicoes Throttled

```promql
# Taxa de requisicoes throttled nos ultimos 5 minutos
rate(rate_limit_requests_total{status="throttled"}[5m])

# Por tenant
sum by (tenant_id) (rate(rate_limit_requests_total{status="throttled"}[5m]))
```

### Tokens Restantes por Tenant

```promql
# Media de tokens restantes
avg by (tenant_id) (rate_limit_tokens_remaining)

# Tenants com menos de 20 tokens (alerta)
rate_limit_tokens_remaining < 20
```

### Percentual de Requisicoes Throttled

```promql
# Percentual de throttled vs total
sum(rate(rate_limit_requests_total{status="throttl ed"}[5m])) /
sum(rate(rate_limit_requests_total[5m])) * 100
```

### Erros Redis

```promql
# Taxa de erros Redis
rate(rate_limit_redis_errors_total[5m])

# Por operacao
sum by (operation) (rate(rate_limit_redis_errors_total[5m]))
```

### Latencia de Rate Limiting

```promql
# Percentil 95 de tempo de espera
histogram_quantile(0.95, rate(rate_limit_wait_duration_seconds_bucket[5m]))

# Media por tenant
avg by (tenant_id) (rate(rate_limit_wait_duration_seconds_sum[5m]) /
                  rate(rate_limit_wait_duration_seconds_count[5m]))
```

## Comandos para Verificar Metricas

### Via curl

```bash
# Obter metricas do endpoint /metrics
curl http://localhost:8003/metrics | grep rate_limit

# Filtrar apenas requests throttled
curl http://localhost:8003/metrics | grep rate_limit_requests_total | grep throttled

# Verificar tokens restantes para tenant especifico
curl http://localhost:8003/metrics | grep rate_limit_tokens_remaining | grep tenant-123
```

### Via promtool

```bash
# Verificar metricas expostas
promtool query instant http://localhost:8003/metrics 'rate_limit_requests_total'

# Query com filtro
promtool query instant http://localhost:8003/metrics \
  'rate(rate_limit_requests_total{status="throttled"}[5m])'
```

### Via Grafana

Importe o dashboard em `docs/grafana/rate_limiting_dashboard.json` (se disponivel) ou crie queries customizadas.

## Troubleshooting

### Problema: Alto Percentual de Throttling

**Sintoma:** Muitas requisicoes retornam HTTP 429

**Diagnostico:**
```promql
# Verificar taxa de throttling
sum(rate(rate_limit_requests_total{status="throttled"}[5m])) /
sum(rate(rate_limit_requests_total[5m])) * 100
```

**Solucoes:**
1. Aumentar `RATE_LIMIT_DEFAULT_CAPACITY`
2. Aumentar `RATE_LIMIT_DEFAULT_REFILL_RATE`
3. Ajustar `RATE_LIMIT_BURST_MULTIPLIER`
4. Revisar limites por tier

### Problema: Redis Connection Errors

**Sintoma:** Logs com `rate_limit_redis_connection_error`

**Diagnostico:**
```promql
# Verificar erros Redis
rate(rate_limit_redis_errors_total[5m])
```

**Solucoes:**
1. Verificar conectividade Redis (`redis-cli ping`)
2. Verificar configuracao `REDIS_URL`
3. Aumentar timeout de conexao
4. Configurar retry/backoff apropriado

**Nota:** Sistema tem comportamento fail-open, entao requisicoes continuam sendo permitidas.

### Problema: Tenants Especificos Sempre Throttled

**Sintoma:** Tenant especifico sempre recebe 429

**Diagnostico:**
```bash
# Verificar tokens no Redis
redis-cli HGETALL "rate_limit:tenant-123:user-456:POST:/api/v1/workflows"
```

**Solucoes:**
1. Resetar bucket manualmente:
```bash
curl -X POST http://localhost:8003/api/v1/admin/rate-limit/reset \
  -H "X-Tenant-ID: tenant-123" \
  -H "X-User-ID: user-456"
```

2. Verificar se tenant esta em tier correto
3. Ajustar limite especifico para tenant

### Problema: Headers de Rate Limit Ausentes

**Sintoma:** Respostas nao contem headers `RateLimit-*`

**Causas Possiveis:**
1. `ENABLE_RATE_LIMITING=false`
2. Middleware nao registrado no FastAPI
3. Ordem de middleware incorreta

**Solucao:**
```python
# Verificar que middleware esta registrado em src/main.py
app.add_middleware(RateLimitMiddleware, redis_client=redis, settings=settings)
```

### Problema: Metricas Nao Aparecem no Prometheus

**Sintoma:** Endpoint `/metrics` nao mostra `rate_limit_*`

**Causas Possiveis:**
1. Middleware de metricas nao registrado
2. Registry Prometheus incorreto
3. Rate limiting desabilitado (sem traffic = sem metricas)

**Solucao:**
```bash
# Verificar se metricas sao expostas
curl http://localhost:8003/metrics | grep rate_limit

# Se vazio, gerar traffic
for i in {1..100}; do
  curl http://localhost:8003/api/v1/health \
    -H "X-Tenant-ID: test" \
    -H "X-User-ID: test"
done
```

## Exemplo de Configuracao Completa

### docker-compose.yml

```yaml
version: '3.8'
services:
  orchestrator-dynamic:
    image: nhm/orchestrator-dynamic:latest
    environment:
      # Feature Flag
      ENABLE_RATE_LIMITING: "true"

      # Configuracoes Padrao
      RATE_LIMIT_DEFAULT_CAPACITY: "500"
      RATE_LIMIT_DEFAULT_REFILL_RATE: "25.0"
      RATE_LIMIT_BURST_MULTIPLIER: "2.0"
      RATE_LIMIT_REDIS_KEY_PREFIX: "rate_limit"

      # Limites por Tier (JSON)
      RATE_LIMIT_TIER_LIMITS: '{
        "premium": {"capacity": 1000, "refill_rate": 50.0, "burst_multiplier": 2.0},
        "standard": {"capacity": 500, "refill_rate": 25.0, "burst_multiplier": 2.0},
        "basic": {"capacity": 100, "refill_rate": 10.0, "burst_multiplier": 1.5}
      }'

      # Redis Connection
      REDIS_URL: "redis://redis:6379/0"
    ports:
      - "8003:8003"
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

### Kubernetes ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orchestrator-rate-limit-config
data:
  ENABLE_RATE_LIMITING: "true"
  RATE_LIMIT_DEFAULT_CAPACITY: "500"
  RATE_LIMIT_DEFAULT_REFILL_RATE: "25.0"
  RATE_LIMIT_BURST_MULTIPLIER: "2.0"
  RATE_LIMIT_TIER_LIMITS: |
    {
      "premium": {"capacity": 1000, "refill_rate": 50.0, "burst_multiplier": 2.0},
      "standard": {"capacity": 500, "refill_rate": 25.0, "burst_multiplier": 2.0},
      "basic": {"capacity": 100, "refill_rate": 10.0, "burst_multiplier": 1.5}
    }
```

## Alertas Prometheus Recomendados

### Alert: Alta Taxa de Throttling

```yaml
- alert: HighRateLimitThrottling
  expr: |
    sum(rate(rate_limit_requests_total{status="throttled"}[5m])) /
    sum(rate(rate_limit_requests_total[5m])) > 0.1
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Alta taxa de throttling (>10%)"
    description: "Tenant {{ $labels.tenant_id }} com {{ $value }}% de throttling"
```

### Alert: Redis Errors

```yaml
- alert: RateLimitRedisErrors
  expr: rate(rate_limit_redis_errors_total[5m]) > 0
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "Erros Redis no rate limiting"
    description: "Operacao {{ $labels.operation }} falhando"
```

## Testes de Carga

### Testar Limite Basico

```bash
# Enviar 150 requisicoes (limite = 100)
for i in {1..150}; do
  curl -w "\nStatus: %{http_code}\n" \
    http://localhost:8003/api/v1/health \
    -H "X-Tenant-ID: load-test" \
    -H "X-User-ID: test-user"
done | grep "Status: 429" | wc -l
# Esperado: ~50 requisicoes com 429
```

### Testar Burst Behavior

```bash
# Enviar burst de 200 requisicoes instantaneas
for i in {1..200}; do
  curl http://localhost:8003/api/v1/health \
    -H "X-Tenant-ID: burst-test" \
    -H "X-User-ID: test-user" &
done
wait

# Verificar quantas passaram (burst multiplier 2.0 = 200)
```

### Testar Refill Rate

```bash
# Esgotar bucket
for i in {1..200}; do
  curl http://localhost:8003/api/v1/health \
    -H "X-Tenant-ID: refill-test" \
    -H "X-User-ID: test-user" &
done
wait

# Aguardar refill (10 tokens/segundo = 100 tokens em 10 segundos)
sleep 10

# Tentar novamente - deve ter tokens disponiveis
curl -v http://localhost:8003/api/v1/health \
  -H "X-Tenant-ID: refill-test" \
  -H "X-User-ID: test-user"
```

## Referencias

- **Spec:** `.agent-os/specs/2026-04-05-token-bucket-rate-limiting/spec.md`
- **Codigo Middleware:** `src/middleware/rate_limit_middleware.py`
- **Codigo Redis Backend:** `src/clients/rate_limit_redis.py`
- **Config por Endpoint:** `src/config/rate_limit_config.py`
- **Metricas:** `src/observability/rate_limit_metrics.py`
