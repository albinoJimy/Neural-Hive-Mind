# Unified Gateway - Guia de Migração

**Versão:** 1.0.0
**Data:** 2026-05-05
**Status:** Staging Deployment

---

## Visão Geral

O Unified Gateway (`:7999`) é o ponto único de entrada para todas as operações do Neural Hive Mind, consolidando:

| Componente | Porta Anterior | Porta Nova | Propósito |
|------------|----------------|------------|-----------|
| Unified Gateway | N/A | `:7999` | Entry point único, auth, rate limiting |
| NLU Service | `gateway-intencoes:8000` | `:8020` | gRPC para NLP/extração de entidades |
| PII Service | `gateway-intencoes:8000` | `:8021` | gRPC para detecção/masking de PII |
| Approval Service | `approval-gateway:8017` | `:8004` | Aprovações via Approval Core Package |

### Benefícios

- **Autenticação centralizada:** JWT validado uma vez no gateway
- **Rate limiting unificado:** 100 req/min por tenant (configurável)
- **Observabilidade:** Distributed tracing via OpenTelemetry
- **Graceful degradation:** Fallback local se NLU/PII services indisponíveis
- **Eliminação de duplicações:** -3.453 LOC de código

---

## Arquitetura

```
                    ┌─────────────────────────────────────────┐
                    │         Unified Gateway (:7999)         │
                    │  - JWT Auth (tenant_id, user_id)       │
                    │  - Rate Limiter (Redis)                │
                    │  - Intent Classifier (NLU gRPC)        │
                    │  - Flow Router (HTTP/gRPC proxy)       │
                    │  - Circuit Breaker (resilience)        │
                    └────────────┬──────────────┬─────────────┘
                                 │              │
                    ┌────────────▼──────┐   ┌──▼──────────────┐
                    │  NLU Service      │   │  PII Service    │
                    │  :8020 (gRPC)     │   │  :8021 (gRPC)   │
                    │  - spaCy models   │   │  - Presidio     │
                    │  - pt/en/es       │   │  - AES-256-GCM  │
                    └───────────────────┘   └─────────────────┘
```

---

## API Endpoints

### Endpoint Principal

```
POST /api/v1/nhm/request
```

**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json
X-Tenant-ID: <tenant_id>  # opcional, extraído do JWT
X-Session-ID: <session_id>  # opcional
```

**Request Body:**
```json
{
  "text": "Quero analisar os dados de vendas do mês passado",
  "context": {
    "domain": "business",
    "language": "pt"
  }
}
```

**Response (200 OK):**
```json
{
  "request_id": "uuid-v4",
  "status": "completed",
  "result": {
    "intent": {
      "domain": "BUSINESS",
      "action": "analyze",
      "entities": ["vendas", "mês passado"],
      "confidence": 0.87
    },
    "flow_type": "A-F",
    "data": { ... }
  },
  "tracing": {
    "trace_id": "...",
    "span_id": "..."
  }
}
```

**Error Responses:**

| Código | Descrição | Headers |
|--------|-----------|---------|
| 401 | JWT inválido/expirado | `WWW-Authenticate: Bearer` |
| 429 | Rate limit excedido | `Retry-After: 60` |
| 503 | Serviço indisponível (circuit open) | `X-Circuit-State: open` |

---

## Endpoints de Saúde

| Endpoint | Propósito |
|----------|-----------|
| `GET /health` | Health check geral |
| `GET /health/ready` | Readiness probe |
| `GET /health/live` | Liveness probe |
| `GET /metrics` | Prometheus metrics |

---

## Migração de Clientes

### Clientes Antigos (gateway-intencoes:8000)

**Antes:**
```python
response = requests.post(
    "http://gateway-intencoes:8000/api/v1/intentions",
    json={"text": "Analisar dados"},
    headers={"Authorization": f"Bearer {token}"}
)
```

**Depois:**
```python
response = requests.post(
    "http://unified-gateway:7999/api/v1/nhm/request",
    json={"text": "Analisar dados"},
    headers={"Authorization": f"Bearer {token}"}
)
# Resultado compatível, mas com campos adicionais
```

### Clientes de Aprovação (approval-gateway:8017)

**Antes:**
```python
response = requests.post(
    "http://approval-gateway:8017/approve",
    json={"plan_id": "123", "decision": "approve"}
)
```

**Depois:**
```python
response = requests.post(
    "http://approval-service:8004/api/v1/approvals/123/approve",
    json={"decision": "approve", "comments": "Approved via API"}
)
# NOTA: Campos renomeados, ver Approval Core Package docs
```

---

## Configuração

### Variáveis de Ambiente

| Variável | Default | Descrição |
|----------|---------|-----------|
| `NLU_SERVICE_ADDRESS` | `nlu-service.nlu.svc.cluster.local:8020` | Endereço gRPC do NLU |
| `PII_SERVICE_ADDRESS` | `pii-service.pii.svc.cluster.local:8021` | Endereço gRPC do PII |
| `CIRCUIT_BREAKER_THRESHOLD` | `5` | Falhas antes de abrir circuito |
| `CIRCUIT_BREAKER_TIMEOUT_SECONDS` | `60` | Tempo até half-open |
| `RATE_LIMIT_REDIS_HOST` | `redis.redis-cluster.svc.cluster.local` | Redis para rate limiting |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `100` | Limite por tenant |

---

## Runbooks

### Circuit Breaker Aberto

**Sintoma:** HTTP 503 com header `X-Circuit-State: open`

**Diagnóstico:**
```bash
# Verificar estado do circuit breaker
kubectl get cm unified-gateway-config -n gateway -o yaml

# Verificar logs do NLU/PII services
kubectl logs -n nlu deployment/nlu-service --tail=100
kubectl logs -n pii deployment/pii-service --tail=100
```

**Resolução:**
1. Verificar saúde dos serviços NLU/PII
2. Se recuperado, aguardar `recovery_timeout` (60s)
3. Se problema persiste, aumentar `failure_threshold`

### Rate Limiting Agressivo

**Sintoma:** HTTP 429 inesperado

**Diagnóstico:**
```bash
# Verificar contadores Redis
redis-cli -h redis.redis-cluster.svc.cluster.local
> GET rate_limit:tenant:123

# Verificar configuração
kubectl get cm unified-gateway-config -n gateway -o yaml | grep RATE_LIMIT
```

**Resolução:**
1. Aumentar `RATE_LIMIT_REQUESTS_PER_MINUTE`
2. Implementar exponential backoff no cliente
3. Usar endpoint `/metrics` para análise

### NLU Service Indisponível

**Sintoma:** Timeout + fallback local ativado

**Diagnóstico:**
```bash
# Verificar pods NLU
kubectl get pods -n nlu -l app=nlu-service

# Verificar se gRPC está respondendo
kubectl exec -n nlu deployment/nlu-service -- curl localhost:8021/health
```

**Resolução:**
1. Verificar recursos (CPU/memory) - HPA pode não estar escalando
2. Reiniciar pods: `kubectl rollout restart deployment/nlu-service -n nlu`
3. Verificar spaCy models carregados nos logs

---

## Deploy

### Staging

```bash
# Via GitHub Actions (automático após push)
gh workflow run build-and-push-ghcr.yml \
  -f services="unified-gateway,nlu-service,pii-service" \
  -f version_tag="v1.0.0"

# Via kubectl manual
kubectl apply -f k8s/unified-gateway-deployment.yaml
kubectl apply -f k8s/nlu-service-deployment.yaml
kubectl apply -f k8s/pii-service-deployment.yaml
```

### Verificação

```bash
# Health checks
curl http://unified-gateway:7999/health
curl http://nlu-service:8021/health
curl http://pii-service:9021/health

# Teste de carga
ab -n 1000 -c 10 -H "Authorization: Bearer $TOKEN" \
   http://unified-gateway:7999/api/v1/nhm/request
```

---

## Rollback

```bash
# Reverter para imagem anterior
kubectl rollout undo deployment/unified-gateway -n gateway
kubectl rollout undo deployment/nlu-service -n nlu
kubectl rollout undo deployment/pii-service -n pii

# Verificar status
kubectl rollout status deployment/unified-gateway -n gateway
```

---

## Suporte

**Issues:** https://github.com/albinoJimy/Neural-Hive-Mind/issues
**Documentation:** `docs/UNIFIED_GATEWAY_MIGRATION.md`
**Spec:** `.agent-os/specs/2026-05-01-unified-gateway-architecture/spec.md`
