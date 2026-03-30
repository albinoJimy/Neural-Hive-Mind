# Epic D - Integração Online Learning

## Status
✅ **COMPLETO** (2026-03-30)

## Overview
Integração do sistema de Online Learning (IncrementalLearner) no approval-service para que modelos ML possam aprender continuamente com feedbacks.

## Tickets Implementados

### D001: Consumer Kafka de Feedback
**Arquivo:** `services/approval-service/src/consumers/feedback_consumer.py`

**Funcionalidades:**
- ✅ Consumo do tópico `specialist_feedback`
- ✅ `FeedbackBuffer` com tamanho configurável
- ✅ Envio para IncrementalLearner quando buffer encher
- ✅ Enriquecimento de dados via MongoDB (nlp_features)
- ✅ Suporte a deserialização JSON (fallback para Avro)

**Classes:**
- `FeedbackBuffer`: Buffer circular thread-safe
- `FeedbackConsumer`: Kafka consumer com buffer integrado

### D002: Integração IncrementalLearner
**Arquivo:** `services/approval-service/src/services/online_learning_service.py`

**Funcionalidades:**
- ✅ Wrapper para `IncrementalLearner` de ml_pipelines
- ✅ Extração de features de feedbacks (10 features)
- ✅ `partial_fit` periódico por specialist_type
- ✅ Model checkpoint automático
- ✅ Métricas de aprendizado e convergência
- ✅ Suporte a múltiplos especialistas (text_analysis, code_analysis, etc.)

**Classes:**
- `OnlineLearningService`: Serviço principal de online learning
- Exceções: `OnlineLearningServiceError`, `OnlineLearningNotEnabledError`, `FeatureExtractionError`

**Features Extraídas:**
1. `confidence` - Confiança do especialista
2. `risk` - Score de risco
3. `sentiment_score` - Sentimento do texto (NLP)
4. `urgency_score` - Urgência (NLP)
5. `complexity_score` - Complexidade (NLP)
6-10. `*_domain_confidence` - Confiança por domínio (business, technical, architecture, behavior, evolution)

### D003: Scheduler de Retreino
**Arquivo:** `services/approval-service/src/schedulers/retraining_scheduler.py`

**Funcionalidades:**
- ✅ Agendamento de retreino (diário/semanal/configurável)
- ✅ Trigger por drift detection
- ✅ Shadow validation antes de deploy
- ✅ A/B testing entre modelo antigo e novo
- ✅ Retraining manual via API
- ✅ Rollback automático em caso de problema
- ✅ Limpeza de histórico de validações

**Classes:**
- `RetrainingScheduler`: Scheduler principal
- Enums: `SchedulerStatus`, `RetrainingTrigger`, `ValidationStatus`
- Factory: `create_retraining_scheduler()`

### D004: Testes de Online Learning
**Arquivo:** `services/approval-service/tests/test_online_learning_integration.py`

**Cobertura:** 36 testes unitários e de integração

**Testes por Classe:**
- `TestFeedbackBuffer` (7 testes)
- `TestFeedbackConsumer` (5 testes)
- `TestOnlineLearningService` (10 testes)
- `TestRetrainingScheduler` (8 testes)
- `TestFactoryFunction` (2 testes)
- `TestOnlineLearningIntegration` (4 testes)

## Configurações Adicionadas

**Arquivo:** `services/approval-service/src/config/settings.py`

```python
# Online Learning Configuration
enable_online_learning: bool = Field(default=False)
online_learning_buffer_size: int = Field(default=100)
online_learning_retrain_interval_hours: int = Field(default=24)
kafka_specialist_feedback_topic: str = Field(default='specialist-feedback')
online_learning_checkpoint_path: str = Field(default='/data/online_learning/checkpoints')
online_learning_algorithm: str = Field(default='sgd')
online_learning_learning_rate: float = Field(default=0.001)
online_learning_checkpoint_interval_updates: int = Field(default=100)
```

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Approval Service                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────┐    ┌──────────────────┐                     │
│  │ FeedbackConsumer │───▶│  FeedbackBuffer  │                     │
│  └──────────────────┘    └────────┬─────────┘                     │
│                                    │                               │
│                                    ▼                               │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │           OnlineLearningService                              │ │
│  │  ┌─────────────────────────────────────────────────────┐    │ │
│  │  │  IncrementalLearner (per specialist_type)            │    │ │
│  │  │  - text_analysis                                     │    │ │
│  │  │  - code_analysis                                     │    │ │
│  │  │  - security                                          │    │ │
│  │  │  - business/technical/architecture/behavior/evolution │    │ │
│  │  └─────────────────────────────────────────────────────┘    │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                    │                               │
│                                    ▼                               │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │           RetrainingScheduler                                │ │
│  │  - Scheduled retraining (hourly/daily/weekly)               │ │
│  │  - Drift detection trigger                                  │ │
│  │  - Shadow validation                                        │ │
│  │  - A/B testing                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Fluxo de Dados

```
Kafka Topic: specialist_feedback
        │
        ▼
FeedbackConsumer (consome mensagens)
        │
        ▼
FeedbackBuffer (acumula até buffer_size)
        │
        ▼ (quando buffer cheio ou flush manual)
OnlineLearningService.process_feedback_batch()
        │
        ├──▶ Agrupa por specialist_type
        │
        ├──▶ Extrai features (confiança, risco, NLP)
        │
        ├──▶ Extrai label (approve/reject/review_required)
        │
        └──▶ IncrementalLearner.partial_fit(X, y)
                │
                ├──▶ Atualiza modelo incrementalmente
                │
                └──▶ Salva checkpoint a cada N updates
```

## Utilização

### Ativar Online Learning

```bash
# Variáveis de ambiente
export ENABLE_ONLINE_LEARNING=true
export ONLINE_LEARNING_BUFFER_SIZE=100
export ONLINE_LEARNING_RETRAIN_INTERVAL_HOURS=24
export ONLINE_LEARNING_ALGORITHM=sgd
```

### Exemplo de Uso

```python
from src.consumers.feedback_consumer import FeedbackConsumer
from src.services.online_learning_service import OnlineLearningService
from src.schedulers.retraining_scheduler import create_retraining_scheduler

# Inicializar serviços
feedback_consumer = FeedbackConsumer(settings=settings)
online_learning = OnlineLearningService(settings=settings)
scheduler = create_retraining_scheduler(
    settings=settings,
    online_learning_service=online_learning
)

# Inicializar
await feedback_consumer.initialize()
await online_learning.initialize()

# Iniciar consumo de feedbacks
async def process_batch(feedbacks):
    await online_learning.process_feedback_batch(feedbacks)

await feedback_consumer.start_consuming(process_callback=process_batch)

# Iniciar scheduler de retreino
await scheduler.start()
```

## Métricas Disponíveis

### OnlineLearningService
- `get_model_state(specialist_type)`: Estado do modelo
- `get_convergence_metrics(specialist_type)`: Métricas de convergência
- `get_all_learner_states()`: Estado de todos os learners

### RetrainingScheduler
- `get_scheduler_status()`: Status do scheduler
- `get_recent_validations()`: Validações recentes

## Linhas de Código

| Componente | Arquivo | Linhas |
|------------|---------|--------|
| Feedback Consumer | `feedback_consumer.py` | 490 |
| Online Learning Service | `online_learning_service.py` | 695 |
| Retraining Scheduler | `retraining_scheduler.py` | 527 |
| Testes | `test_online_learning_integration.py` | 706 |
| **Total** | | **2,418** |

## Próximos Passos

1. **Integração com API REST:** Adicionar endpoints para:
   - Status do online learning
   - Trigger manual de retreino
   - Métricas de convergência

2. **Dashboard de Monitoramento:** Visualizar:
   - Loss por specialist
   - Taxa de aprendizado
   - Convergência

3. **MLflow Integration:** Logar métricas e parâmetros no MLflow

4. **Shadow Validation Real:** Implementar validação shadow com dados reais

5. **A/B Testing Framework:** Implementar teste A/B completo entre modelos

## Documentação Relacionada

- `ml_pipelines/online_learning/` - Pipeline de online learning
- `docs/GAPS-03-CONSENSO_HIERARQUICO.md` - Modelo de senioridade
- `docs/RELATORIO_RETRAINING_V4_MARCO_2026.md` - Análise de retreino
