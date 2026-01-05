# Rate Limiting no Gateway de Intencoes

## Visao Geral

O Gateway de Intencoes implementa rate limiting por usuario usando **Sliding Window Counter** com Redis.
Esta abordagem garante distribuicao justa de recursos e protecao contra abuso do sistema.

## Algoritmo

O rate limiter utiliza o algoritmo de **Sliding Window Counter** com as seguintes caracteristicas:

- **Janela de tempo**: 1 minuto
- **Contador atomico**: Operacoes Redis INCR + EXPIRE
- **TTL automatico**: Limpeza automatica de contadores expirados
- **Hierarquia de limites**: Usuario > Tenant > Global

## Configuracao

### Variaveis de Ambiente

```bash
# Habilitar rate limiting
RATE_LIMIT_ENABLED=true

# Limite global (requisicoes por minuto)
RATE_LIMIT_REQUESTS_PER_MINUTE=1000

# Burst capacity
RATE_LIMIT_BURST_SIZE=100

# Comportamento em caso de falha do Redis
# true = permitir requisicoes (fail-open)
# false = bloquear requisicoes (fail-closed)
RATE_LIMIT_FAIL_OPEN=true

# Limites por tenant (JSON)
RATE_LIMIT_TENANT_OVERRIDES='{"premium-tenant": 5000, "basic-tenant": 500}'

# Limites por usuario (JSON)
RATE_LIMIT_USER_OVERRIDES='{"admin-user": 10000}'
```

## Headers de Resposta

Todas as respostas autenticadas incluem headers de rate limit:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 750
X-RateLimit-Reset: 1704067200
```

| Header | Descricao |
|--------|-----------|
| `X-RateLimit-Limit` | Limite total de requisicoes por minuto |
| `X-RateLimit-Remaining` | Requisicoes restantes na janela atual |
| `X-RateLimit-Reset` | Unix timestamp quando o limite sera resetado |

## Resposta 429 (Rate Limit Exceeded)

Quando o limite e excedido, a API retorna:

```json
{
  "error": "authentication_failed",
  "message": "Rate limit excedido. Tente novamente em 45s"
}
```

Headers adicionais:
```
Retry-After: 45
```

## Hierarquia de Limites

Os limites sao aplicados na seguinte ordem de prioridade:

1. **Limite por usuario especifico** (mais prioritario)
2. **Limite por tenant**
3. **Limite global padrao**

Exemplo:
- Usuario `admin` tem limite de 10000 req/min
- Tenant `premium` tem limite de 5000 req/min
- Limite global: 1000 req/min

Se `admin` pertence ao tenant `premium`, seu limite sera 10000 (limite do usuario tem prioridade).

## Fail-Open vs Fail-Closed

| Modo | Comportamento | Recomendacao |
|------|---------------|--------------|
| Fail-Open (default) | Permite requisicoes se Redis falhar | Desenvolvimento, staging |
| Fail-Closed | Bloqueia requisicoes se Redis falhar | Producao com alta seguranca |

## Metricas Prometheus

```promql
# Total de requisicoes bloqueadas por rate limiting
gateway_rate_limit_exceeded_total{limit_type, tenant_id}

# Duracao da verificacao de rate limit (segundos)
gateway_rate_limit_check_duration_seconds

# Uso atual do rate limit por tenant
gateway_rate_limit_current_usage{tenant_id}
```

### Exemplos de Queries

```promql
# Taxa de requisicoes bloqueadas por rate limit
rate(gateway_rate_limit_exceeded_total[5m])

# P95 da duracao de verificacao de rate limit
histogram_quantile(0.95, rate(gateway_rate_limit_check_duration_seconds_bucket[5m]))

# Tenants com maior uso de rate limit
topk(5, gateway_rate_limit_current_usage)
```

## Testes de Carga

```bash
# Testar rate limiting
python tests/performance/gateway-load-test.py \
  --url http://localhost:8000 \
  --token $AUTH_TOKEN \
  --test-rate-limit \
  --rate-limit-user test_user \
  --expected-rate-limit 1000
```

## Integracao com Kubernetes

O rate limiter e configurado via Helm chart:

```yaml
# helm-charts/gateway-intencoes/values.yaml
rateLimit:
  enabled: true
  requestsPerMinute: 1000
  burstSize: 100
  failOpen: true
  tenantOverrides:
    premium-tenant: 5000
    basic-tenant: 500
  userOverrides:
    admin-user: 10000
```

## Troubleshooting

### Rate limit atingido muito rapido

1. Verificar `RATE_LIMIT_REQUESTS_PER_MINUTE`
2. Verificar se ha configuracao de tenant/usuario
3. Verificar logs para identificar usuario afetado

### Rate limit nao funcionando

1. Verificar se `RATE_LIMIT_ENABLED=true`
2. Verificar conectividade com Redis
3. Verificar logs de erro do rate limiter

### Latencia alta no rate limiting

1. Verificar metrica `gateway_rate_limit_check_duration_seconds`
2. Verificar latencia do Redis
3. Considerar usar Redis local ou com menor latencia
