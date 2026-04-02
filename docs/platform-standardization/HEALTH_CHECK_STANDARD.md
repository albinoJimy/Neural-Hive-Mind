# Padrao Health Check - Neural-Hive-Mind

## Visao Geral

Este documento define o padrao de implementacao de endpoints de health check para todos os servicos do Neural-Hive-Mind. Health checks sao essenciais para:

- Orquestracao Kubernetes (liveness/readiness probes)
- Monitoramento e alertas
- Load balancing e graceful degradation
- Debugging em producao

## Endpoints Obrigatorios

Todo servico deve expor os seguintes endpoints:

### 1. GET /health
**Proposito:** Status agregado do servico para monitoramento humano

**Response:**
```json
{
  "status": "healthy|degraded|unhealthy",
  "service": "service-name",
  "version": "1.0.0",
  "timestamp": "2026-04-02T12:00:00Z",
  "checks": {
    "database": {
      "status": "healthy",
      "latency_ms": 5
    },
    "kafka": {
      "status": "healthy",
      "latency_ms": 2
    },
    "redis": {
      "status": "degraded",
      "latency_ms": 150
    }
  }
}
```

### 2. GET /health/live
**Proposito:** Liveness probe do Kubernetes - determina se o pod deve ser reiniciado

**Response:**
```json
{
  "status": "alive"
}
```

**Comportamento:**
- Retorna `200 OK` com `{"status": "alive"}` se o servico esta rodando
- Retorna `503 Service Unavailable` se o servico estiver em crash loop

### 3. GET /health/ready
**Proposito:** Readiness probe do Kubernetes - determina se o pod pode receber traffic

**Response:**
```json
{
  "status": "ready",
  "dependencies": {
    "database": "ready",
    "kafka": "ready",
    "redis": "not_ready"
  }
}
```

**Comportamento:**
- Retorna `200 OK` se TODAS as dependencias criticas estao disponiveis
- Retorna `503 Service Unavailable` se alguma dependencia critica falhar

## Definicao de Status

| Status | Descricao | Acao Kubernetes |
|--------|-----------|-----------------|
| `healthy` | Todas as checks passaram | Nenhuma |
| `degraded` | Checks nao-criticas falharam | Nenhuma (log warning) |
| `unhealthy` | Checks criticas falharam | Reiniciar pod |

## Dependencias Criticas vs Nao-Criticas

**Criticas** (falha = unhealthy):
- Database (MongoDB, PostgreSQL)
- Message broker (Kafka, RabbitMQ)
- Cache principal (Redis)

**Nao-Criticas** (falha = degraded):
- Servicos externos (APIs de terceiros)
- Feature flags
- Armazenamento de objetos (S3)

## Implementacao

### Uso Basico

```python
from neural_hive_api.health import HealthRouter
from fastapi import FastAPI

app = FastAPI()

# Criar router de health
health_router = HealthRouter(
    service_name="my-service",
    version="1.0.0"
)

# Adicionar checks
health_router.add_check("database", check_database)
health_router.add_check("kafka", check_kafka, critical=True)
health_router.add_check("external_api", check_external_api, critical=False)

# Registrar router
app.include_router(health_router.router, prefix="/health", tags=["health"])
```

### Check Customizado

```python
async def check_database() -> HealthCheckResult:
    try:
        start = time.time()
        await database.ping()
        latency = (time.time() - start) * 1000

        if latency > 100:
            return HealthCheckResult(
                status="degraded",
                latency_ms=latency,
                message="High latency"
            )

        return HealthCheckResult(
            status="healthy",
            latency_ms=latency
        )
    except Exception as e:
        return HealthCheckResult(
            status="unhealthy",
            message=str(e)
        )
```

## Configuracao Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-service
spec:
  template:
    spec:
      containers:
      - name: my-service
        image: my-service:latest
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 2
```

## Boas Praticas

1. **Timeouts:** Checks devem ter timeout maximo de 5 segundos
2. **Caching:** Resultado dos checks pode ser cacheado por 5-10 segundos
3. **Logging:** Falhas devem ser logged com contexto suficiente
4. **Idempotencia:** Endpoints devem ser idempotentes e stateless
5. **Autenticacao:** Endpoints de health NAO devem requerer autenticacao

## Monitoramento

Configurar alertas baseados nos endpoints:

- **Alerta Critico:** `/health` retorna `unhealthy` por mais de 2 minutos
- **Alerta de Warning:** `/health` retorna `degraded` por mais de 10 minutos
- **Metricas:** Exportar duracao dos checks para Prometheus

## Referencias

- `libraries/python/neural_hive_api/neural_hive_api/health.py`
- Kubernetes probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
