# API Specification

This is the API specification for the spec detailed in @.agent-os/specs/2026-03-17-active-learning-feedback/spec.md

## Endpoints

### GET /api/v1/active-learning/metrics

**Purpose:** Retorna métricas de balanceamento do dataset de feedback

**Parameters:** None

**Response:**
```json
{
  "total_feedbacks": 484,
  "balance": {
    "approve": {"count": 450, "percentage": 93.0, "gap": 0.0},
    "reject": {"count": 34, "percentage": 7.0, "gap": 43.0},
    "review_required": {"count": 0, "percentage": 0.0, "gap": 20.0}
  },
  "confidence_distribution": {
    "low": {"count": 242, "percentage": 50.0},
    "medium": {"count": 242, "percentage": 50.0},
    "high": {"count": 0, "percentage": 0.0}
  },
  "domain_distribution": {
    "technical": {"count": 120, "percentage": 24.8},
    "business": {"count": 80, "percentage": 16.5},
    "security": {"count": 15, "percentage": 3.1, "gap": 16.9}
  },
  "semantic_features_count": 46,
  "semantic_features_percentage": 9.5,
  "priority_recommendations": [
    {"type": "class", "value": "reject", "gap": 43.0},
    {"type": "confidence", "value": "high", "gap": 20.0},
    {"type": "domain", "value": "security", "gap": 16.9}
  ],
  "last_updated": "2026-03-17T10:30:00Z"
}
```

**Errors:**
- 500: Erro interno ao calcular métricas

### GET /api/v1/active-learning/queue

**Purpose:** Retorna próximos casos na fila de revisão prioritária

**Parameters:**
- `limit` (query, optional): Máximo de casos a retornar (default: 10, max: 50)
- `status` (query, optional): Filtrar por status (default: "pending")

**Response:**
```json
{
  "queue_size": 12,
  "cases": [
    {
      "queue_id": "queue-abc123",
      "plan_id": "plan-123",
      "intent_preview": "Implementar autenticação...",
      "information_value": 0.85,
      "priority_reason": "high_uncertainty_low_representation",
      "predicted_decision": "reject",
      "confidence": 0.45,
      "domain": "security",
      "created_at": "2026-03-17T10:00:00Z",
      "status": "pending"
    }
  ],
  "filters_applied": {
    "limit": 10,
    "status": "pending"
  }
}
```

**Errors:**
- 400: Parâmetros inválidos
- 500: Erro interno ao buscar fila

### POST /api/v1/active-learning/{queue_id}/claim

**Purpose:** Marca caso da fila como "em revisão" para evitar conflitos

**Parameters:**
- `queue_id` (path): ID do caso na fila

**Request Body:**
```json
{
  "assigned_to": "user@example.com"
}
```

**Response:**
```json
{
  "queue_id": "queue-abc123",
  "plan_id": "plan-123",
  "status": "in_review",
  "assigned_to": "user@example.com",
  "claimed_at": "2026-03-17T10:35:00Z",
  "expires_at": "2026-03-17T11:35:00Z"
}
```

**Errors:**
- 404: Caso não encontrado ou já processado
- 409: Caso já está em revisão por outro usuário
- 500: Erro interno ao reivindicar caso

### POST /api/v1/active-learning/{queue_id}/feedback

**Purpose:** Submete feedback manual para caso prioritário e marca como completo

**Parameters:**
- `queue_id` (path): ID do caso na fila

**Request Body:**
```json
{
  "human_recommendation": "reject",
  "human_rating": 0.2,
  "feedback_notes": "A análise de segurança está incompleta...",
  "submitted_by": "user@example.com"
}
```

**Response:**
```json
{
  "feedback_id": "feedback-xyz789",
  "queue_id": "queue-abc123",
  "plan_id": "plan-123",
  "status": "completed",
  "balanced_dataset": true,
  "information_value": 0.85,
  "submitted_at": "2026-03-17T10:40:00Z"
}
```

**Errors:**
- 400: Dados de feedback inválidos
- 404: Caso não encontrado
- 500: Erro interno ao submeter feedback

### POST /api/v1/active-learning/{queue_id}/release

**Purpose:** Libera caso da fila (ex: usuário decidiu não revisar)

**Parameters:**
- `queue_id` (path): ID do caso na fila

**Response:**
```json
{
  "queue_id": "queue-abc123",
  "status": "pending",
  "released_at": "2026-03-17T10:45:00Z"
}
```

**Errors:**
- 404: Caso não encontrado
- 500: Erro interno ao liberar caso

## Controllers

### ActiveLearningController (services/approval-service/src/api/routers/active_learning.py)

- `get_metrics()`: Busca métricas do DatasetBalanceAnalyzer
- `get_queue(limit, status)`: Busca casos da PriorityFeedbackQueue
- `claim_case(queue_id, assigned_to)`: Marca caso como em revisão
- `submit_feedback(queue_id, feedback_data)`: Submete feedback via FeedbackCollector
- `release_case(queue_id)`: Libera caso da fila

### Business Logic

- **Claim expira após 1 hora**: Caso não for submetido feedback, volta para "pending"
- **Rate limiting**: Máximo 5 claims simultâneos por usuário
- **Validação**: Apenas usuário que fez claim pode submeter feedback
- **Tratamento de erros**: Rollback de status em caso de falha

## Purpose

Esses endpoints permitem:
1. Data Scientists monitorarem balanceamento do dataset em tempo real
2. Engenheiros obterem fila de casos prioritários ordenada por valor informacional
3. Usuários reivindicarem casos para revisão sem conflitos
4. Feedbacks coletados serem marcados como "balanceados" para retreino ML
