# Evolution Hooks - Meta-learning para Evolution Specialist

## Visão Geral

O **Evolution Hooks** é um sistema de meta-learning que permite ao Evolution Specialist aprender quais heurísticas funcionam melhor para quais tipos de planos, adaptando seus pesos dinamicamente baseado em histórico de avaliações.

### Funcionalidades

- **Fingerprint Extraction**: Extrai assinatura compacta de planos cognitivos
- **Pattern Matching**: Busca planos similares no histórico MongoDB
- **Weight Adaptation**: Ajusta pesos de avaliação baseado em taxa de sucesso
- **Feedback Loop**: Consome feedback do Kafka para aprendizado contínuo

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                    Evolution Specialist                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. FingerprintExtractor.extract(plan)                           │
│     └─> Fingerprint {domain, priority, task_count_range, ...}   │
│                                                                   │
│  2. PatternMatcher.find_similar(fingerprint)                     │
│     └─> List[PatternRecord] (histórico MongoDB)                 │
│                                                                   │
│  3. WeightAdapter.adapt_weights(fingerprint)                     │
│     └─> Dict[str, float] (pesos adaptados)                       │
│                                                                   │
│  4. Evaluation com pesos adaptados                                │
│     └─> EvolutionEvaluation {confidence, risk, ...}              │
│                                                                   │
│  5. PatternRegistry.store_evaluation(...)                        │
│     └─> MongoDB (pattern_registry collection)                    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Kafka Topic                                   │
│                    evolution.feedback.topic                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              EvolutionFeedbackConsumer                           │
│                                                                   │
│  - Consome mensagens de feedback                                 │
│  - Atualiza métricas de padrões                                  │
│  - Calcula novas taxas de sucesso                                │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Componentes

### FingerprintExtractor

Extrai assinatura compacta do plano cognitivo.

```python
from neural_hive_specialists.evolution_hooks import FingerprintExtractor

extractor = FingerprintExtractor()
fingerprint = extractor.extract(cognitive_plan)

# Fingerprint(
#     domain='technical',
#     priority='high',
#     task_count_range=<TaskCountRange.MEDIUM: 'medium'>,
#     task_types=['BUILD', 'TEST', 'DEPLOY'],
#     avg_dependency_count=1.5,
#     has_conditional_deps=True,
#     estimated_duration_range=<DurationRange.MEDIUM: 'medium'>,
#     complexity_signature='T-M-B-T-D-M'
# )
```

### PatternMatcher

Busca planos similares no histórico MongoDB.

```python
from neural_hive_specialists.evolution_hooks import PatternMatcher

matcher = PatternMatcher(mongo_client)
similar = await matcher.find_similar(
    fingerprint,
    limit=10,
    min_similarity=0.7
)

# Retorna List[PatternRecord]
```

### WeightAdapter

Ajusta pesos baseado em histórico de sucesso.

```python
from neural_hive_specialists.evolution_hooks import WeightAdapter

adapter = WeightAdapter(
    mongo_client,
    min_similar_patterns=5,
    max_adjustment=0.05
)

adaptive_weights = await adapter.adapt_weights(fingerprint)

# {
#     'maintainability': 0.27,      # +0.02 (alto sucesso)
#     'scalability': 0.23,          # -0.02 (baixo sucesso)
#     'extensibility': 0.20,
#     'modularity': 0.15,
#     'tech_debt_prevention': 0.15
# }
```

### PatternRegistry

Repository para armazenar e recuperar padrões.

```python
from neural_hive_specialists.evolution_hooks import SyncPatternRegistry
from neural_hive_specialists.evolution_hooks import PatternRecord, Fingerprint, EvolutionEvaluation

registry = SyncPatternRegistry(
    mongo_client,
    database='neural_hive',
    collection='pattern_registry'
)

# Armazenar avaliação
pattern_id = registry.store_evaluation(
    plan_id='plan-123',
    fingerprint=fingerprint,
    evaluation=evolution_evaluation
)

# Buscar por plan_id
record = registry.get_by_plan_id('plan-123')
```

### EvolutionFeedbackConsumer

Consome feedback do Kafka para aprendizado.

```python
from neural_hive_specialists.evolution_hooks import create_feedback_consumer

consumer = await create_feedback_consumer(
    bootstrap_servers='localhost:9092',
    group_id='evolution-feedback-consumer',
    mongo_client=mongo_client
)

await consumer.start()
```

## Configuração

### Environment Variables

```bash
# Habilita evolution hooks
EVOLUTION_HOOKS_ENABLED=true

# Configurações de matching
EVOLUTION_HOOKS_MIN_SIMILAR_PATTERNS=5
EVOLUTION_HOOKS_MAX_ADJUSTMENT=0.05

# Database
EVOLUTION_HOOKS_PATTERN_REGISTRY_DB=neural_hive
EVOLUTION_HOOKS_PATTERN_REGISTRY_COLLECTION=pattern_registry

# Kafka
EVOLUTION_FEEDBACK_KAFKA_BOOTSTRAP_SERVERS=localhost:9092
EVOLUTION_FEEDBACK_KAFKA_GROUP_ID=evolution-feedback-consumer
EVOLUTION_FEEDBACK_KAFKA_TOPIC=evolution.feedback.topic
```

### Specialist Config

```python
from services.specialist_evolution.src.config import EvolutionSpecialistConfig

config = EvolutionSpecialistConfig(
    # Evolution Hooks
    evolution_hooks_enabled=True,
    evolution_hooks_min_similar_patterns=5,
    evolution_hooks_max_adjustment=0.05,
    evolution_hooks_pattern_registry_db='neural_hive',

    # Kafka (para feedback consumer)
    kafka_bootstrap_servers='localhost:9092',
    kafka_feedback_topic='evolution.feedback.topic',
    kafka_group_id='evolution-feedback-consumer'
)
```

## MongoDB Schema

### Collection: `pattern_registry`

```javascript
{
  "_id": ObjectId("..."),
  "plan_id": "plan-uuid-123",
  "fingerprint": {
    "domain": "technical",
    "priority": "high",
    "task_count_range": "medium",
    "task_types": ["BUILD", "TEST", "DEPLOY"],
    "avg_dependency_count": 1.5,
    "has_conditional_deps": true,
    "estimated_duration_range": "medium",
    "complexity_signature": "T-M-B-T-D-M"
  },
  "evaluation": {
    "confidence_score": 0.75,
    "risk_score": 0.25,
    "recommendation": "approve",
    "weights_used": {
      "maintainability": 0.25,
      "scalability": 0.25,
      "extensibility": 0.20,
      "modularity": 0.15,
      "tech_debt_prevention": 0.15
    },
    "reasoning_factors": [...]
  },
  "feedback": {
    "outcome": "approve",
    "source": "human",
    "reasoning": "Approved after review",
    "timestamp": "2026-03-24T10:00:00Z"
  },
  "metrics": {
    "times_matched": 10,
    "success_rate": 0.85,
    "last_updated": "2026-03-24T10:00:00Z"
  },
  "created_at": "2026-03-24T09:00:00Z",
  "updated_at": "2026-03-24T10:00:00Z"
}
```

### Indices

```javascript
db.pattern_registry.createIndex({"fingerprint.complexity_signature": 1})
db.pattern_registry.createIndex({"plan_id": 1}, {unique: true})
db.pattern_registry.createIndex({"fingerprint.domain": 1, "fingerprint.priority": 1})
db.pattern_registry.createIndex({"metrics.success_rate": -1})
```

## Kafka Topic

### Topic: `evolution.feedback.topic`

Schema da mensagem:

```json
{
  "plan_id": "plan-uuid-123",
  "fingerprint": {
    "domain": "technical",
    "priority": "high",
    "task_count_range": "medium",
    "task_types": ["BUILD", "TEST", "DEPLOY"],
    "avg_dependency_count": 1.5,
    "has_conditional_deps": true,
    "complexity_signature": "T-M-B-T-D-M"
  },
  "evaluation": {
    "confidence_score": 0.75,
    "risk_score": 0.25,
    "recommendation": "approve",
    "weights_used": {...},
    "reasoning_factors": [...]
  },
  "feedback": {
    "outcome": "approve",
    "source": "human",
    "reasoning": "Approved after review",
    "timestamp": "2026-03-24T10:00:00Z"
  }
}
```

## Uso

### Integration no Evolution Specialist

O Evolution Specialist já integra evolution hooks automaticamente quando habilitado:

```python
# services/specialist-evolution/src/specialist.py

class EvolutionSpecialist(BaseSpecialist):
    def __init__(self, config):
        super().__init__(config)
        self._init_evolution_hooks()

    def _init_evolution_hooks(self):
        if not EVOLUTION_HOOKS_AVAILABLE:
            return
        if not config.evolution_hooks_enabled:
            return

        self._fingerprint_extractor = FingerprintExtractor()
        self._pattern_registry = SyncPatternRegistry(...)
        self._pattern_matcher = PatternMatcher(...)
        self._weight_adapter = WeightAdapter(...)
```

### Avaliação com Pesos Adaptativos

```python
async def _get_adaptive_weights(self, cognitive_plan):
    if not self._evolution_hooks_enabled:
        return self.DEFAULT_WEIGHTS.copy()

    fingerprint = self._fingerprint_extractor.extract(cognitive_plan)
    adapted = await self._weight_adapter.adapt_weights(fingerprint)

    return adapted
```

### Armazenamento para Aprendizado

```python
async def _store_evaluation_for_learning(
    self,
    plan_id: str,
    cognitive_plan: Dict,
    evaluation_result: Dict
):
    if not self._evolution_hooks_enabled:
        return

    fingerprint = self._fingerprint_extractor.extract(cognitive_plan)
    evolution_eval = EvolutionEvaluation(...)

    self._pattern_registry.store_evaluation(
        plan_id=plan_id,
        fingerprint=fingerprint,
        evaluation=evolution_eval
    )
```

## Troubleshooting

### Evolution Hooks não inicializa

**Problema**: Logs mostram "Evolution hooks disabled in config"

**Solução**:
```bash
# Verificar environment variable
export EVOLUTION_HOOKS_ENABLED=true

# Ou set no config
config.evolution_hooks_enabled = True
```

### Pesos sempre são defaults

**Problema**: `adaptive_weights == DEFAULT_WEIGHTS` sempre

**Causas possíveis**:
1. Mongo client não disponível
2. Padrões insuficientes no histórico
3. Erro no weight adaptation

**Solução**:
```python
# Verificar logs
logger.debug("Evolution hooks enabled", enabled=self._evolution_hooks_enabled)

# Verificar mongo connection
if self.mongo_client is None:
    logger.warning("Mongo client not available")
```

### Feedback Consumer não processa mensagens

**Problema**: Mensagens no Kafka não são consumidas

**Solução**:
```bash
# Verificar topic
kafka-topics.sh --list --bootstrap-server localhost:9092

# Verificar consumer group
kafka-consumer-groups.sh --describe --group evolution-feedback-consumer \
  --bootstrap-server localhost:9092
```

### Baixa similaridade encontrada

**Problema**: `find_similar()` retorna lista vazia

**Causa**: Histórico insuficiente ou fingerprints muito diferentes

**Solução**:
```python
# Ajustar threshold
similar = await matcher.find_similar(
    fingerprint,
    min_similarity=0.5  # reduzir de 0.7 para 0.5
)

# Ou usar pesos defaults quando similares < min_similar_patterns
if len(similar) < config.evolution_hooks_min_similar_patterns:
    return self.DEFAULT_WEIGHTS.copy()
```

## Métricas

O sistema expõe métricas para monitoramento:

- `evolution_hooks_enabled` - Gauge (0 ou 1)
- `evolution_hooks_pattern_match_count` - Histograma
- `evolution_hooks_weight_adjustment` - Gauge por dimensão
- `evolution_hooks_adaptation_rate` - Taxa de adaptações bem-sucedidas

## Referências

- Código: `libraries/python/neural_hive_specialists/evolution_hooks/`
- Testes: `libraries/python/neural_hive_specialists/tests/evolution_hooks/`
- Specialist: `services/specialist-evolution/src/specialist.py`
- Migration: `libraries/python/neural_hive_specialists/evolution_hooks/migrations/m001_create_pattern_registry.py`
