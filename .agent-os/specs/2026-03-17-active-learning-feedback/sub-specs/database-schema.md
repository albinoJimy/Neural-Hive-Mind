# Database Schema

This is the database schema implementation for the spec detailed in @.agent-os/specs/2026-03-17-active-learning-feedback/spec.md

## Changes

### Nova Coleção: active_learning_queue

Armazena planos cognitivos que precisam de revisão manual priorizada.

### Novos Campos: specialist_feedback

Adiciona campos para rastrear feedbacks coletados via active learning.

## Specifications

### Coleção: active_learning_queue

```javascript
// Estrutura do documento
{
  _id: ObjectId,
  queue_id: String,  // "queue-" + UUID
  plan_id: String,   // FK para plan_approvals
  intent_text: String,
  intent_preview: String,  // Primeiros 100 caracteres
  information_value: Number,  // 0.0-1.0, calculado pela estratégia
  priority_reason: String,   // Descrição do porquê é prioritário
  domain: String,  // primary_domain das NLP features
  confidence: Number,  // Confiança da predição ML
  predicted_decision: String,  // "approve" ou "reject"
  status: String,  // "pending", "in_review", "completed", "cancelled"
  assigned_to: String,  // Email do usuário que fez claim
  claimed_at: ISODate,
  expires_at: ISODate,  // Claim expira após 1 hora
  completed_at: ISODate,
  feedback_id: String,  // FK para specialist_feedback quando completado
  created_at: ISODate,
  updated_at: ISODate,
  metadata: {
    nlp_features: Object,  // Snapshot das features NLP
    class_gap: Number,  // Gap de representação da classe
    domain_gap: Number,  // Gap de representação do domínio
    uncertainty_score: Number  // 1.0 - confidence
  }
}

// Índices
db.active_learning_queue.createIndex({ queue_id: 1 }, { unique: true })
db.active_learning_queue.createIndex({ plan_id: 1 }, { unique: true })
db.active_learning_queue.createIndex({ information_value: -1, status: 1 })
db.active_learning_queue.createIndex({ status: 1, created_at: 1 })
db.active_learning_queue.createIndex({ assigned_to: 1, status: 1 })
db.active_learning_queue.createIndex({ expires_at: 1 }, { sparse: true, expireAfterSeconds: 3600 })
```

### Modificação: specialist_feedback

Adiciona campos para rastrear origem do feedback e valor informacional.

```javascript
// Novos campos (adicionar ao schema existente)
{
  balanced_dataset: Boolean,  // default: false
  information_value: Number,  // optional, 0.0-1.0
  active_learning_queue_id: String,  // optional, FK para active_learning_queue
  auto_generated: Boolean,  // Já existe, manter
  manual_review: Boolean,  // Já existe, manter
  collection_method: String,  // "automatic", "active_learning", "manual"
  reviewed_by: String,  // Email do revisor (se aplicável)
  reviewed_at: ISODate  // Timestamp da revisão manual
}

// Índice novo
db.specialist_feedback.createIndex({ balanced_dataset: 1 })
db.specialist_feedback.createIndex({ collection_method: 1, submitted_at: -1 })
db.specialist_feedback.createIndex({ active_learning_queue_id: 1 }, { sparse: true })
```

## Rationale

**active_learning_queue:**
- Índice composto `(information_value: -1, status: 1)` permite buscas eficientes dos próximos casos prioritários
- TTL index em `expires_at` limpa claims expirados automaticamente
- Índice em `assigned_to` permite listar casos em revisão por usuário

**specialist_feedback:**
- Campo `balanced_dataset` permite filtrar feedbacks para retreino balanceado
- Campo `information_value` permite ordenar feedbacks por valor
- Campo `collection_method` rastreia origem do feedback para análise

## Performance Considerations

- Índices garantem queries < 100ms para até 10.000 documentos na fila
- TTL index evita acúmulo de claims expirados
- Coleção `active_learning_queue` deve crescer para ~1000 documentos (1 semana de operação)
- Índice composto em `(information_value, status)` é crítico para performance
