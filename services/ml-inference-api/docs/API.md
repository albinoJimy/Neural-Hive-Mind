# API REST - ML Inference API

Documentação completa da API REST do serviço de inferência ML.

## Índice

- [Visão Geral](#visão-geral)
- [Autenticação](#autenticação)
- [Rate Limiting](#rate-limiting)
- [Endpoints](#endpoints)
  - [Health & Metrics](#health--metrics)
  - [Inferência](#inferência)
- [Schemas](#schemas)
- [Códigos de Erro](#códigos-de-erro)
- [Exemplos](#exemplos)

---

## Visão Geral

A API fornece endpoints para predição ML de aprovação de planos cognitivos, processamento em batch e monitorização de saúde do serviço.

**URL Base:** `http://localhost:8010`

**Versão da API:** v1

**Content-Type:** `application/json`

---

## Autenticação

Atualmente, a autenticação JWT é **opcional** e configurável via `ENABLE_AUTH`.

```bash
# Exemplo de header com autenticação (quando habilitado)
Authorization: Bearer <jwt_token>
```

### Configuração

| Variável | Descrição | Default |
|----------|-----------|---------|
| `ENABLE_AUTH` | Habilita autenticação JWT | `false` |
| `JWT_SECRET_KEY` | Chave secreta para assinatura | `change-me-in-production` |
| `JWT_ALGORITHM` | Algoritmo de assinatura | `HS256` |

---

## Rate Limiting

A API implementa rate limiting via SlowAPI para prevenir abuso.

### Configuração

| Variável | Descrição | Default |
|----------|-----------|---------|
| `ENABLE_RATE_LIMITING` | Habilita rate limiting | `true` |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | Requests por minuto por IP | `60` |

### Comportamento

Quando o limite é excedido, a API retorna:

```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests - please try again later",
  "detail": "Rate limit exceeded: 60 per 1 minute"
}
```

**HTTP Status:** `429 Too Many Requests`

---

## Endpoints

### Health & Metrics

#### GET /health

Liveness probe - verifica se o serviço está rodando.

**Response:** `200 OK`

```json
{
  "status": "healthy",
  "service": "ml-inference-api",
  "version": "1.0.0"
}
```

---

#### GET /ready

Readiness probe - verifica dependências críticas (modelo ML, circuit breaker).

**Response:** `200 OK` ou `503 Service Unavailable`

```json
{
  "status": "ready",
  "checks": {
    "ml_model": true,
    "circuit_breaker_closed": true
  }
}
```

---

#### GET /metrics

Métricas Prometheus em formato de texto.

**Response:** `200 OK` (text/plain)

Exemplo de métricas:

```
# HELP model_loaded Se o modelo ML está carregado
# TYPE model_loaded gauge
model_loaded 1.0

# HELP predictions_total Total de predições realizadas
# TYPE predictions_total counter
predictions_total{decision="approve"} 1234
predictions_total{decision="reject"} 56
predictions_total{decision="review_required"} 12

# HELP prediction_duration_seconds Duração da predição
# TYPE prediction_duration_seconds histogram
prediction_duration_seconds_bucket{le="0.001"} 0
prediction_duration_seconds_bucket{le="0.005"} 10
...
```

---

#### GET /model-info

Retorna informações detalhadas sobre o modelo carregado.

**Response:** `200 OK`

```json
{
  "is_loaded": true,
  "name": "nhm_approval_model",
  "version": "v7",
  "type": "GradientBoostingClassifier",
  "trained_at": "2026-03-16T10:00:00Z",
  "training_samples": 46,
  "features": [
    "confidence",
    "risk",
    "specialist_confidence",
    "rf_ml_confidence",
    "rf_ml_risk"
  ],
  "metrics": {
    "f1_score": 0.5115,
    "accuracy": 0.6495
  },
  "loading_time_ms": 245.3
}
```

---

#### GET /circuit-breaker

Retorna estado atual do circuit breaker.

**Response:** `200 OK`

```json
{
  "name": "ml_inference",
  "state": "CLOSED",
  "failure_count": 0,
  "threshold": 5,
  "last_failure_time": null,
  "last_state_change": 1712345678.123
}
```

**Estados possíveis:**
- `CLOSED` (0): Funcionamento normal
- `OPEN` (1): Rejeitando chamadas
- `HALF_OPEN` (2): Testando recuperação

---

### Inferência

#### POST /api/v1/inference/predict

Predição individual de aprovação para uma intenção.

**Request Body:**

```json
{
  "intent_text": "Create new user with email verification and password hashing",
  "specialist_confidence": 0.75,
  "specialist_type": "security",
  "options": {
    "return_probabilities": true,
    "return_features": false,
    "threshold": 0.7
  }
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `intent_text` | string | Sim | Texto da intenção (1-5000 caracteres) |
| `specialist_confidence` | float | Não | Confiança do especialista (0.0-1.0). Default: 0.5 |
| `specialist_type` | string | Não | Tipo de especialista (para tracing) |
| `options` | object | Não | Opções adicionais |
| `options.return_probabilities` | boolean | Não | Retornar probabilidades. Default: true |
| `options.return_features` | boolean | Não | Retornar features extraídas. Default: false |
| `options.threshold` | float | Não | Threshold customizado para decisão |

**Response:** `200 OK`

```json
{
  "decision": "approve",
  "confidence": 0.92,
  "probabilities": {
    "approve": 0.92,
    "reject": 0.05,
    "review_required": 0.03
  },
  "features": null,
  "model_version": "v7",
  "inference_time_ms": 15.3,
  "timestamp": "2026-04-04T10:30:00Z"
}
```

**Decisões possíveis:**
- `approve`: Aprovar automaticamente
- `reject`: Rejeitar automaticamente
- `review_required`: Requer revisão humana

---

#### POST /api/v1/inference/predict-batch

Processa múltiplas predições em paralelo.

**Request Body:**

```json
{
  "requests": [
    {
      "intent_text": "Create new user with email verification",
      "specialist_confidence": 0.75,
      "specialist_type": "security"
    },
    {
      "intent_text": "Delete all records without backup",
      "specialist_confidence": 0.5,
      "specialist_type": "analyst"
    }
  ],
  "options": {
    "parallel": true,
    "max_workers": 4,
    "aggregate_results": true
  }
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `requests` | array | Sim | Lista de requests (máx: 100) |
| `options` | object | Não | Opções de batch |
| `options.parallel` | boolean | Não | Processar em paralelo. Default: true |
| `options.max_workers` | integer | Não | Máximo de workers |
| `options.aggregate_results` | boolean | Não | Agregar estatísticas. Default: true |

**Response:** `200 OK`

```json
{
  "results": [
    {
      "decision": "approve",
      "confidence": 0.88,
      "probabilities": {
        "approve": 0.88,
        "reject": 0.08,
        "review_required": 0.04
      },
      "model_version": "v7",
      "inference_time_ms": 12.5,
      "timestamp": "2026-04-04T10:30:00Z"
    },
    {
      "decision": "reject",
      "confidence": 0.95,
      "probabilities": {
        "approve": 0.02,
        "reject": 0.95,
        "review_required": 0.03
      },
      "model_version": "v7",
      "inference_time_ms": 14.2,
      "timestamp": "2026-04-04T10:30:00Z"
    }
  ],
  "total_processed": 2,
  "successful": 2,
  "failed": 0,
  "aggregate_stats": {
    "decision_counts": {
      "approve": 1,
      "reject": 1
    },
    "average_confidence": 0.915,
    "average_inference_time_ms": 13.35,
    "total_inference_time_ms": 26.7
  },
  "total_inference_time_ms": 26.7,
  "timestamp": "2026-04-04T10:30:00Z"
}
```

---

#### POST /api/v1/inference/circuit-breaker/reset

Reseta manualmente o circuit breaker (apenas admin).

**ATENÇÃO:** Este endpoint deve ser protegido em produção.

**Response:** `200 OK`

```json
{
  "status": "reset",
  "message": "Circuit breaker has been reset to CLOSED state"
}
```

---

## Schemas

### PredictRequest

```typescript
{
  intent_text: string              // 1-5000 caracteres
  specialist_confidence: float     // 0.0 - 1.0, default: 0.5
  specialist_type?: string         // opcional, para tracing
  options?: {
    return_probabilities: boolean  // default: true
    return_features: boolean       // default: false
    threshold?: float             // threshold customizado
  }
}
```

### PredictResponse

```typescript
{
  decision: "approve" | "reject" | "review_required"
  confidence: float                // 0.0 - 1.0
  probabilities?: {
    approve: float
    reject: float
    review_required: float
  }
  features?: Record<string, float> // se solicitado
  model_version: string
  inference_time_ms: float
  timestamp: string                // ISO 8601
}
```

### BatchPredictRequest

```typescript
{
  requests: PredictRequest[]        // 1-100 itens
  options?: {
    parallel: boolean              // default: true
    max_workers?: integer
    aggregate_results: boolean     // default: true
  }
}
```

### BatchPredictResponse

```typescript
{
  results: PredictResponse[]
  total_processed: integer
  successful: integer
  failed: integer
  aggregate_stats?: {
    decision_counts: Record<string, integer>
    average_confidence: float
    average_inference_time_ms: float
    total_inference_time_ms: float
  }
  total_inference_time_ms: float
  timestamp: string
}
```

---

## Códigos de Erro

| Código | Descrição | Quando ocorre |
|--------|-----------|---------------|
| `200` | OK | Request bem-sucedido |
| `400` | Bad Request | Parâmetros inválidos |
| `429` | Too Many Requests | Rate limit excedido |
| `500` | Internal Server Error | Erro interno do serviço |
| `503` | Service Unavailable | Circuit breaker aberto ou serviço não inicializado |

### ErrorResponse Schema

```typescript
{
  error: string                   // Tipo do erro
  message: string                 // Mensagem detalhada
  detail?: string                 // Detalhes adicionais
  timestamp: string               // ISO 8601
}
```

### Exemplos de Erro

**400 Bad Request:**

```json
{
  "error": "validation_error",
  "message": "intent_text must be between 1 and 5000 characters",
  "timestamp": "2026-04-04T10:30:00Z"
}
```

**503 Service Unavailable (Circuit Breaker):**

```json
{
  "error": "service_unavailable",
  "message": "ML inference circuit breaker is open - service temporarily unavailable",
  "timestamp": "2026-04-04T10:30:00Z"
}
```

---

## Exemplos

### cURL

#### Predição Individual

```bash
curl -X POST http://localhost:8010/api/v1/inference/predict \
  -H "Content-Type: application/json" \
  -d '{
    "intent_text": "Create new user with email verification and password hashing",
    "specialist_confidence": 0.75,
    "specialist_type": "security"
  }'
```

#### Predição com Threshold Customizado

```bash
curl -X POST http://localhost:8010/api/v1/inference/predict \
  -H "Content-Type: application/json" \
  -d '{
    "intent_text": "Deploy to production without tests",
    "specialist_confidence": 0.6,
    "options": {
      "threshold": 0.8
    }
  }'
```

#### Predição em Batch

```bash
curl -X POST http://localhost:8010/api/v1/inference/predict-batch \
  -H "Content-Type: application/json" \
  -d '{
    "requests": [
      {
        "intent_text": "Create user account",
        "specialist_confidence": 0.8
      },
      {
        "intent_text": "Delete database",
        "specialist_confidence": 0.3
      }
    ],
    "options": {
      "parallel": true
    }
  }'
```

#### Health Check

```bash
curl http://localhost:8010/health
```

#### Circuit Breaker Status

```bash
curl http://localhost:8010/circuit-breaker
```

### Python (requests)

```python
import requests

# Predição individual
response = requests.post(
    "http://localhost:8010/api/v1/inference/predict",
    json={
        "intent_text": "Create new user with email verification",
        "specialist_confidence": 0.75,
        "specialist_type": "security"
    }
)
result = response.json()
print(f"Decision: {result['decision']}, Confidence: {result['confidence']}")
```

### JavaScript (fetch)

```javascript
// Predição individual
const response = await fetch('http://localhost:8010/api/v1/inference/predict', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    intent_text: 'Create new user with email verification',
    specialist_confidence: 0.75,
    specialist_type: 'security'
  })
});

const result = await response.json();
console.log(`Decision: ${result.decision}, Confidence: ${result.confidence}`);
```

### Go (net/http)

```go
package main

import (
    "bytes"
    "encoding/json"
    "net/http"
)

func main() {
    data := map[string]interface{}{
        "intent_text":           "Create new user",
        "specialist_confidence": 0.75,
        "specialist_type":       "security",
    }
    jsonData, _ := json.Marshal(data)

    resp, _ := http.Post(
        "http://localhost:8010/api/v1/inference/predict",
        "application/json",
        bytes.NewBuffer(jsonData),
    )
    defer resp.Close()

    var result map[string]interface{}
    json.NewDecoder(resp.Body).Decode(&result)
    println(result["decision"], result["confidence"])
}
```

---

## Fluxo de Integração

Diagrama de fluxo típico de uma predição:

```
┌─────────────┐     POST /predict      ┌──────────────┐
│   Cliente   │ ────────────────────> │ ML Inference │
└─────────────┘                        └──────────────┘
                                              │
                                              ▼
                                      ┌───────────────┐
                                      │ Rate Limiter   │
                                      └───────────────┘
                                              │
                                              ▼
                                      ┌───────────────┐
                                      │ Circuit       │
                                      │ Breaker       │
                                      └───────────────┘
                                              │
                                              ▼
                                      ┌───────────────┐
                                      │ Feature       │
                                      │ Extraction    │
                                      └───────────────┘
                                              │
                                              ▼
                                      ┌───────────────┐
                                      │ ML Model      │
                                      │ Prediction    │
                                      └───────────────┘
                                              │
                                              ▼
                                      ┌───────────────┐
                                      │ Response +    │
                                      │ Metrics       │
                                      └───────────────┘
```

---

## Links Relacionados

- [Deployment Guide](./DEPLOYMENT.md)
- [Development Guide](./DEVELOPMENT.md)
- [Metrics Documentation](./METRICS.md)
- [README Principal](../README.md)
