# Technical Specification

This is the technical specification for the spec detailed in @.agent-os/specs/2026-03-17-active-learning-feedback/spec.md

## Technical Requirements

### DatasetBalanceAnalyzer (libraries/python/neural_hive_specialists/feedback/)

- **calculate_balance_metrics()**: Analisa coleção `specialist_feedback` e retorna métricas de balanceamento
  - Distribuição por `human_recommendation` (approve/reject/review_required)
  - Distribuição por faixas de `opinion_confidence` (0.0-0.3, 0.3-0.7, 0.7-1.0)
  - Distribuição por `nlp_features.primary_domain`
  - Contagem de feedbacks com `reasoning_factors` semânticos
  - Identifica classes sub-representadas (< 20% do dataset)

- **get_priority_recommendations()**: Retorna lista de tipos de feedback prioritários
  - Ordena por gap de representação
  - Considera confiança do modelo
  - Retorna domínios com menos de 10 samples

### PriorityFeedbackQueue (libraries/python/neural_hive_specialists/feedback/)

- **enqueue_plan_for_review(plan_id, intent_text, prediction)**: Adiciona plano à fila de revisão
  - Calcula "information_value" baseado em:
    - `prediction.confidence` (quanto menor, maior valor)
    - `prediction.decision` (reject tem maior prioridade)
    - `nlp_features.primary_domain` (domínios raros têm maior valor)
  - Persiste em MongoDB com índice em `information_value`

- **dequeue_next_case()**: Retorna próximo caso prioritário
  - Busca documento com maior `information_value` não processado
  - Marca como `in_review`
  - Remove da fila após feedback submetido

- **mark_feedback_submitted(feedback_id)**: Marca caso como processado

### ActiveLearningStrategy (libraries/python/neural_hive_specialists/feedback/)

- **calculate_information_value(case)**: Calcula valor informacional (0.0-1.0)
  ```python
  value = (
      (1.0 - confidence) * 0.5 +  # Incerteza (50%)
      (1.0 - representation) * 0.3 +  # Representação (30%)
      domain_novelty * 0.2  # Novidade do domínio (20%)
  )
  ```

- **should_collect_feedback(case)**: Decide se coletar feedback manual
  - Retorna True se `information_value > threshold` (configurável, padrão 0.6)

### API Endpoints (services/approval-service/src/api/routers/)

- **GET /api/v1/active-learning/metrics**: Métricas de balanceamento
  ```json
  {
    "total_feedbacks": 484,
    "balance": {
      "approve": {"count": 450, "percentage": 93.0},
      "reject": {"count": 34, "percentage": 7.0},
      "review_required": {"count": 0, "percentage": 0.0}
    },
    "confidence_distribution": {
      "low": {"count": 242, "percentage": 50.0},
      "medium": {"count": 242, "percentage": 50.0},
      "high": {"count": 0, "percentage": 0.0}
    },
    "semantic_features_count": 46,
    "priority_recommendations": ["reject", "low_confidence", "domain:security"]
  }
  ```

- **GET /api/v1/active-learning/queue**: Próximos casos prioritários
  ```json
  {
    "queue_size": 12,
    "cases": [
      {
        "plan_id": "plan-123",
        "intent_text": "...",
        "information_value": 0.85,
        "reason": "high_uncertainty_low_representation"
      }
    ]
  }
  ```

- **POST /api/v1/active-learning/feedback**: Submete feedback manual para caso prioritário

### Integration Points

- **ApprovalService**: Chama `enqueue_plan_for_review()` quando approval request é criado
- **FeedbackCollector**: Marca feedback com `balanced_dataset=True` quando coletado via active learning
- **MLPredictorService**: Fornece confiança para cálculo de information_value

### Performance Criteria

- Análise de balanceamento: < 500ms para dataset de 1000 samples
- Enqueue/dequeue: < 100ms
- API endpoints: < 200ms p95

## Database Schema

### Nova coleção: active_learning_queue

```javascript
{
  _id: ObjectId,
  plan_id: String (indexed),
  intent_text: String,
  information_value: Float (indexed, descending),
  priority_reason: String,
  domain: String,
  confidence: Float,
  predicted_decision: String,
  created_at: ISODate,
  status: String ("pending", "in_review", "completed"),
  assigned_to: String (optional),
  completed_at: ISODate (optional)
}

// Índices
db.active_learning_queue.createIndex({ information_value: -1, status: 1 })
db.active_learning_queue.createIndex({ plan_id: 1 }, { unique: true })
db.active_learning_queue.createIndex({ status: 1, created_at: 1 })
```

### Modificação em specialist_feedback

- Adicionar campo `balanced_dataset: Boolean` (default: false)
- Adicionar campo `information_value: Float` (optional)
- Adicionar campo `active_learning_queue_id: ObjectId` (optional)

## External Dependencies

Nenhuma dependência externa nova. Utilizar bibliotecas existentes:
- `pymongo` para persistência
- `pydantic` para validação
- `structlog` para logging
