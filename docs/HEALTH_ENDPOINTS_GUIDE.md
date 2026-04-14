# Health Endpoints Guide

## Overview

Todos os serviços FastAPI do Neural Hive-Mind implementam 3 endpoints de saúde padronizados para Kubernetes probes.

## Endpoints

### `/health` - Liveness Probe

Verifica se o processo está vivo.

**Resposta esperada:**
```json
{
  "status": "healthy",
  "service": "<service-name>",
  "version": "1.0.0"
}
```

### `/ready` - Readiness Probe

Verifica se o serviço está pronto para receber tráfego (dependências conectadas).

**Resposta esperada:**
```json
{
  "ready": true,
  "checks": {
    "mongodb": true,
    "redis": true,
    "kafka": true
  }
}
```

**Status codes:**
- `200` - Pronto para tráfego
- `503` - Não pronto (alguma dependência falhou)

### `/health/startup` - Startup Probe (HA-001)

Indica que o serviço completou a inicialização.

**Resposta esperada:**
```json
{
  "status": "started",
  "service": "<service-name>",
  "version": "1.0.0",
  "started_at": "2026-04-14T22:00:00Z"
}
```

## Kubernetes Probes Configuration

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 30
  periodSeconds: 30
  timeoutSeconds: 10

readinessProbe:
  httpGet:
    path: /ready
    port: http
  initialDelaySeconds: 20
  periodSeconds: 10
  timeoutSeconds: 5

startupProbe:
  httpGet:
    path: /health/startup
    port: http
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 6  # 60s total startup time
```

## Serviços

| Serviço | Porta | /health | /ready | /health/startup |
|---------|-------|--------|--------|-----------------|
| consensus-engine | 8002 | ✅ | ✅ | ✅ |
| semantic-translation-engine | 8001 | ✅ | ✅ | ✅ |
| worker-agents | 8005 | ✅ | ✅ | ✅ |
| scout-agents | 8100 | ✅ | ✅ | ✅ |
| queen-agent | 8006 | ✅ | ✅ | ✅ |
| self-healing-engine | 8106 | ✅ | ✅ | ✅ |
| analyst-agents | 8107 | ✅ | ✅ | ✅ |
| execution-ticket-service | 8108 | ✅ | ✅ | ✅ |
| specialist-architecture | 8101 | ✅ | ✅ | ✅ |
| specialist-business | 8102 | ✅ | ✅ | ✅ |
| specialist-technical | 8103 | ✅ | ✅ | ✅ |
| specialist-behavior | 8104 | ✅ | ✅ | ✅ |
| specialist-evolution | 8105 | ✅ | ✅ | ✅ |
| approval-service | 8080 | ✅ | ✅ | ✅ |
| gateway-intencoes | 8000 | ✅ | ✅ | ✅ |

## Testing

```bash
# Test local service
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/health/startup

# Test pod in Kubernetes
kubectl exec -it <pod-name> -- curl http://localhost:8000/health/startup
```

## Troubleshooting

**Pod em CrashLoopBackOff:**
1. Verificar logs: `kubectl logs <pod-name>`
2. Startup probe pode estar falhando antes do serviço completar inicialização
3. Aumentar `failureThreshold` ou `initialDelaySeconds` se necessário

**Readiness failing:**
1. Verificar dependências (MongoDB, Redis, Kafka)
2. Logs mostrarão qual dependência está falhando

**Liveness failing:**
1. Processo pode ter travado
2. Verificar uso de recursos (CPU/memory)
