# Active Learning Feedback Collector - Relatório Final

> Status: ✅ COMPLETO
> Data: 2026-03-17
> Testes: 76/76 passando

## Visão Geral

Implementação completa do sistema de **Active Learning** para coleta de feedbacks balanceados, resolvendo o problema de dataset desbalanceado que afetava a qualidade do modelo ML de aprovação.

## Problema Resolvido

### Situação Anterior
- Apenas 9.5% dos feedbacks tinham features semânticas (46/484)
- Dataset desbalanceado: 93% approve vs 7% reject
- Confiança constante 0.5 em dados históricos (sintéticos)
- Casos de rejeição sub-representados

### Solução Implementada
Sistema de Active Learning que:
1. **Identifica casos sub-representados** - Analisa gap de balanceamento
2. **Calcula valor informacional** - Fórmula ponderada (incerteza + representação + novidade)
3. **Gerencia fila de prioridade** - MongoDB-backed com TTL
4. **Fornece API REST** - Endpoints para revisão manual
5. **Marca feedbacks balanceados** - `balanced_dataset=true`

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Approval Service                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────┐    ┌──────────────────┐    ┌────────────────┐   │
│  │   Kafka      │───▶│ ApprovalRequest  │───▶│ ActiveLearning│   │
│  │   Consumer   │    │     Processor     │    │   Strategy    │   │
│  └─────────────┘    └──────────────────┘    └────────┬───────┘   │
│                                                     │              │
│                           ┌───────────────────────┴───────┐   │
│                           ▼                              │   │
│                  ┌─────────────────────┐              │   │
│                  │  PriorityFeedback    │              │   │
│                  │        Queue          │◀─────────────┘   │
│                  └──────────┬───────────┘              │   │
│                             │                             │   │
│                             ▼                             │   │
│                  ┌─────────────────────┐              │   │
│                  │  Active Learning     │              │   │
│                  │       API Router     │              │   │
│                  └─────────────────────┘              │   │
│                             │                             │   │
│                             ▼                             │   │
│                  ┌─────────────────────┐              │   │
│                  │  MongoDB              │              │   │
│                  │  - active_learning_queue│            │   │
│                  │  - specialist_feedback │            │   │
│                  └─────────────────────┘              │   │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

## Componentes Implementados

### 1. DatasetBalanceAnalyzer
**Arquivo:** `neural_hive_specialists/feedback/active_learning/balance_analyzer.py`

```python
class DatasetBalanceAnalyzer:
    def calculate_balance_metrics() -> BalanceMetrics
    def get_priority_recommendations() -> List[PriorityRecommendation]
```

**Métricas calculadas:**
- Distribuição por classe (approve/reject)
- Distribuição por confiança (low/medium/high)
- Distribuição por domínio
- Features semânticas coverage
- Gaps de balanceamento

### 2. ActiveLearningStrategy
**Arquivo:** `neural_hive_specialists/feedback/active_learning/learning_strategy.py`

```python
class ActiveLearningStrategy:
    async def calculate_information_value(
        plan_id, intent_text, predicted_decision, confidence, domain
    ) -> float
```

**Fórmula de valor informacional:**
```
value = uncertainty × 0.5 + (1 - representation) × 0.3 + novelty × 0.2
```

### 3. PriorityFeedbackQueue
**Arquivo:** `neural_hive_specialists/feedback/active_learning/feedback_queue.py`

```python
class PriorityFeedbackQueue:
    async def enqueue_plan_for_review(...)
    async def dequeue_next_case(...)
    async def claim_case(queue_id, assigned_to)
    async def release_case(queue_id)
    async def mark_feedback_submitted(queue_id, feedback_id)
```

**Schema da fila:**
- `queue_id` (unique)
- `plan_id`
- `information_value` (0-1)
- `status` (pending/in_review/completed/cancelled)
- `expires_at` (TTL de 1 hora)

### 4. API REST
**Arquivo:** `services/approval-service/src/api/routers/active_learning.py`

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/v1/active-learning/metrics` | GET | Métricas de balanceamento |
| `/api/v1/active-learning/queue` | GET | Casos pendentes (ordenados) |
| `/{queue_id}/claim` | POST | Reivindicar caso |
| `/{queue_id}/feedback` | POST | Submeter feedback |
| `/{queue_id}/release` | POST | Liberar caso |

### 5. Integração ApprovalService
**Arquivo:** `services/approval-service/src/services/approval_service.py`

```python
# Enqueue automático em process_approval_request()
await self._maybe_enqueue_for_active_learning(approval_request)

# Marcação de feedback
await self._submit_feedback_for_plan(..., from_active_learning=True)
```

## MongoDB Schema

### Coleção: active_learning_queue
```javascript
{
  queue_id: "queue-abc123",  // unique
  plan_id: "plan-xyz",
  intent_preview: "Implementar...",
  information_value: 0.85,
  priority_reason: "alta incerteza + domínio raro",
  status: "pending",
  expires_at: ISODate("2026-03-17T20:00:00Z"),
  created_at: ISODate("2026-03-17T19:00:00Z")
}
```

**Índices:**
- `idx_queue_id` (unique)
- `idx_status`
- `idx_expires_at` (TTL 3600s)
- `idx_status_info_value_created` (composto)
- `idx_domain`, `idx_confidence`, `idx_predicted_decision`

### Coleção: specialist_feedback (campos novos)
```javascript
{
  // ... campos existentes ...
  balanced_dataset: true,      // NOVO
  collection_method: "active_learning",  // NOVO
  information_value: 0.85       // NOVO (opcional)
}
```

## Testes

### neural_hive_specialists: 55 testes
- `test_dataset_balance_analyzer.py`: 14 ✅
- `test_active_learning_strategy.py`: 19 ✅
- `test_feedback_queue.py`: 22 ✅

### approval-service: 21 testes
- `test_active_learning_router.py`: 10 ✅
- `test_active_learning_integration.py`: 4 ✅
- `test_active_learning_e2e.py`: 7 ✅

## Deploy

### Variáveis de Ambiente
```bash
ENABLE_ACTIVE_LEARNING=true
ACTIVE_LEARNING_MIN_INFORMATION_VALUE=0.5
ACTIVE_LEARNING_ENQUEUE_RATE=0.2
ACTIVE_LEARNING_QUEUE_COLLECTION=active_learning_queue
```

### Migration
```bash
python -m src.database.migrations.m001_active_learning_schema
```

### Kubernetes
```yaml
# ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: approval-service-config
data:
  ENABLE_ACTIVE_LEARNING: "true"
  ACTIVE_LEARNING_MIN_INFORMATION_VALUE: "0.5"
```

## Integração v8 - Retraining com Dataset Balanceado

### Script de Retraining v8
**Arquivo:** `ml_pipelines/training/retrain_v8_balanced.py`

```python
# Carrega apenas feedbacks coletados via Active Learning
query = {
    'nlp_features': {'$exists': True, '$ne': {}},
    'final_decision': {'$exists': True, '$ne': None, '$ne': ''},
    'balanced_dataset': True  # ← Filtro Active Learning
}
```

**Features:**
- Filtro `balanced_dataset=True` para dataset de qualidade
- Suporte a RandomForest e GradientBoosting
- Estatísticas de balanceamento por classe
- Feature `information_value` incluída no treinamento
- Metadata de versão no MongoDB

**Uso:**
```bash
# Dry run para verificar dados disponíveis
python ml_pipelines/training/retrain_v8_balanced.py --dry-run

# Treinar com dados balanceados
python ml_pipelines/training/retrain_v8_balanced.py --model-type random_forest

# Treinar com todos os dados (para comparação)
python ml_pipelines/training/retrain_v8_balanced.py --all-data
```

## Próximos Passos

1. **Coleta de dados reais** - Habilitar em staging para coletar feedbacks balanceados
2. **Acumular amostras balanceadas** - Aguardar ~50-100 feedbacks com `balanced_dataset=True`
3. **Executar retraining v8** - Treinar modelo com dataset balanceado
4. **Monitoramento** - Configurar dashboard Grafana
5. **Comparação v7 vs v8** - A/B test para validar melhoria

## Documentação

- Deploy Guide: `services/approval-service/docs/ACTIVE_LEARNING_DEPLOY.md`
- Dashboard: `services/approval-service/docs/ACTIVE_LEARNING_DASHBOARD.json`
- Spec: `.agent-os/specs/2026-03-17-active-learning-feedback/`

---

**Implementado por:** Claude (Agent OS)
**Data de conclusão:** 2026-03-17
**Status:** Pronto para deploy em staging
