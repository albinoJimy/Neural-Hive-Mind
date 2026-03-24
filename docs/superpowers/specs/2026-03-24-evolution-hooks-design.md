# Evolution Hooks - Meta-Learning Design Document

**Project:** Neural-Hive-Mind
**Component:** Evolution Specialist - Evolution Hooks
**Date:** 2026-03-24
**Status:** Design Approved
**Author:** Claude (AI Assistant)

---

## Overview

Implementar **Evolution Hooks** com meta-learning para o Evolution Specialist, permitindo que ele aprenda quais heurísticas funcionam melhor para quais tipos de planos e adapte seus pesos dinamicamente baseado em histórico de avaliações.

**Problema:** O Evolution Specialist usa pesos fixos para avaliar planos, ignorando que diferentes tipos de planos podem requerer diferentes critérios de avaliação.

**Solução:** Um sistema de meta-learning que mantém um registry de padrões históricos e ajusta os pesos das heurísticas baseado no sucesso de planos similares.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Evolution Specialist                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  CognitivePlan ──►  FingerprintExtractor                            │
│                        ↓                                            │
│                    [fingerprint]                                    │
│                        ↓                                            │
│              PatternMatchRegistry                                   │
│                  /           \                                       │
│         [similar]        [no similar]                               │
│            ↓                  ↓                                     │
│    AdaptiveWeights    DefaultWeights                                │
│    (histórico)         (heurísticas)                                │
│            \              /                                           │
│             ↓            ↓                                            │
│         EvolutionEvaluator (usa pesos ajustados)                    │
│                 ↓                                                   │
│           SpecialistOpinion                                         │
│                 ↓                                                   │
│        ┌──────────────────────┐                                     │
│        │  FeedbackCollector   │ ◄─── Approval Service feedback     │
│        └──────────────────────┘                                     │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Components

1. **FingerprintExtractor** - Extrai assinatura do plano (domínio, complexidade, tipos de tarefas)
2. **PatternMatchRegistry** - MongoDB com histórico de avaliações e fingerprints
3. **AdaptiveWeights** - Ajusta pesos baseado em histórico de planos similares
4. **FeedbackCollector** - Consome feedback do Approval Service e atualiza o registry

---

## Fingerprint and Matching

### Fingerprint Structure

```python
{
    "domain": "technical",           # Domínio do plano
    "priority": "high",              # Prioridade
    "task_count_range": "medium",    # small(<5), medium(5-20), large(>20)
    "task_types": ["BUILD", "TEST", "DEPLOY"],  # Tipos únicos de tarefas
    "avg_dependency_count": 1.5,     # Média de dependências
    "has_conditional_deps": true,    # Tem dependências condicionais?
    "estimated_duration_range": "medium",  # Duração estimada
    "complexity_signature": "M-S-T-H-M"  # Signature baseada em hash de features
}
```

### Matching Algorithm

```python
def find_similar_plans(fingerprint, limit=50):
    """
    Encontra planos similares no histórico usando:
    1. Match exato em domain
    2. Similaridade em task_types (Jaccard)
    3. Proximidade em task_count_range e complexity_signature
    """
    query = {
        "domain": fingerprint["domain"],
        "complexity_signature": {"$regex": f"^{fingerprint['complexity_signature'][:3]}"}
    }
    # Ordena por similaridade Jaccard de task_types
```

### Weight Adjustment

Para planos similares com histórico de sucesso:
- Se `maintainability` foi consistente nos sucessos → aumenta peso (ex: 0.25 → 0.30)
- Se `tech_debt_prevention` teve alta correlação com rejects → diminui peso

---

## Feedback Loop

### Sources

```
Approval Service ──Kafka──► evolution.feedback.topic
                                    ↓
                        FeedbackConsumer (Evolution Specialist)
                                    ↓
                        ┌───────────┴───────────┐
                        │                       │
                   [approve]              [reject]
                        │                       │
           +pesos usados no sucesso    -pesos usados na falha
                        │                       │
                        └───────────┬───────────┘
                                    ↓
                        PatternMatchRegistry (MongoDB)
```

### Feedback Structure

```python
{
    "plan_id": "uuid",
    "fingerprint": {...},
    "weights_used": {
        "maintainability": 0.30,
        "scalability": 0.25,
        "extensibility": 0.20,
        "modularity": 0.15,
        "tech_debt_prevention": 0.10
    },
    "original_recommendation": "approve",
    "final_outcome": "approve",
    "feedback_source": "human",
    "reasoning_factors": [...],
    "timestamp": "2026-03-24T10:00:00Z"
}
```

### Weight Update Algorithm

```python
def update_weights(fingerprint, outcome):
    similar = find_similar_plans(fingerprint, limit=50)

    if len(similar) < 5:  # Dados insuficientes
        return DEFAULT_WEIGHTS

    weight_performance = {}
    for weight_name in ["maintainability", "scalability", "extensibility",
                        "modularity", "tech_debt_prevention"]:
        success_when_high = count_successes(similar, weight_name, "high")
        success_when_low = count_successes(similar, weight_name, "low")

        if success_when_high > success_when_low:
            adjustment = min(0.05, (success_when_high - success_when_low) / 100)
            weight_performance[weight_name] = +adjustment
        else:
            adjustment = min(0.05, (success_when_low - success_when_high) / 100)
            weight_performance[weight_name] = -adjustment

    return apply_adjustments(DEFAULT_WEIGHTS, weight_performance)
```

---

## Database Schema

### Collection: `evolution_pattern_registry`

```javascript
{
  _id: ObjectId,

  // Fingerprint do plano
  fingerprint: {
    domain: String,
    priority: String,
    task_count_range: String,
    task_types: [String],
    avg_dependency_count: Number,
    has_conditional_deps: Boolean,
    complexity_signature: String
  },

  // Avaliação original
  evaluation: {
    confidence_score: Number,
    risk_score: Number,
    recommendation: String,
    weights_used: {
      maintainability: Number,
      scalability: Number,
      extensibility: Number,
      modularity: Number,
      tech_debt_prevention: Number
    },
    reasoning_factors: [Object]
  },

  // Feedback final
  feedback: {
    outcome: String,
    source: String,
    corrected_weights: {Object},
    timestamp: ISODate
  },

  // Contadores para matching
  metrics: {
    times_matched: Number,
    success_rate: Number,
    last_updated: ISODate
  },

  created_at: ISODate,
  updated_at: ISODate
}
```

### Indexes

```javascript
// Matching rápido
{ "fingerprint.domain": 1, "fingerprint.complexity_signature": 1 }

// Analytics
{ "feedback.outcome": 1, "created_at": -1 }
{ "metrics.times_matched": -1 }

// TTL - remove registros antigos com poucos matches
{ "created_at": 1 }, { expireAfterSeconds: 7776000 }  // 90 dias
```

---

## Code Components

### Directory Structure

```
neural_hive_specialists/
├── evolution_hooks/
│   ├── __init__.py
│   ├── fingerprint_extractor.py   # Extrai assinatura do plano
│   ├── pattern_matcher.py          # Busca planos similares
│   ├── weight_adapter.py           # Ajusta pesos baseado em histórico
│   └── feedback_consumer.py        # Consome feedback do Kafka
│
└── evolution_hooks_db/
    ├── __init__.py
    ├── pattern_registry.py         # Repository MongoDB
    └── models.py                   # Pydantic models
```

### Key Interfaces

```python
# fingerprint_extractor.py
class FingerprintExtractor:
    def extract(self, cognitive_plan: Dict) -> Fingerprint:
        """Extrai fingerprint do CognitivePlan"""

# pattern_matcher.py
class PatternMatcher:
    def find_similar(self, fingerprint: Fingerprint, limit: int) -> List[PatternRecord]:
        """Busca planos similares no registry"""

# weight_adapter.py
class WeightAdapter:
    def adapt_weights(self, fingerprint: Fingerprint) -> Dict[str, float]:
        """Retorna pesos ajustados baseado em histórico"""

# feedback_consumer.py
class EvolutionFeedbackConsumer:
    async def consume(self):
        """Consome mensagens do Kafka e atualiza registry"""
```

---

## Integration with Evolution Specialist

### Modified Evaluation Flow

```python
class EvolutionSpecialist(BaseSpecialist):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Novos componentes de evolution hooks
        self.fingerprint_extractor = FingerprintExtractor()
        self.pattern_matcher = PatternMatcher(self.mongo_client)
        self.weight_adapter = WeightAdapter(self.pattern_matcher)

    def _evaluate_plan_internal(self, cognitive_plan, context):
        # 1. Extrair fingerprint
        fingerprint = self.fingerprint_extractor.extract(cognitive_plan)

        # 2. Buscar padrões similares e ajustar pesos
        adaptive_weights = self.weight_adapter.adapt_weights(fingerprint)

        # 3. Usar pesos adaptados em vez de defaults
        maintainability_score = self._analyze_maintainability(tasks, cognitive_plan)
        scalability_score = self._analyze_scalability(tasks, cognitive_plan)
        extensibility_score = self._analyze_extensibility(tasks, cognitive_plan)
        modularity_score = self._analyze_modularity(tasks)
        tech_debt_score = self._analyze_tech_debt_risk(tasks, cognitive_plan)

        # Pesos adaptativos
        confidence_score = (
            maintainability_score * adaptive_weights['maintainability'] +
            scalability_score * adaptive_weights['scalability'] +
            extensibility_score * adaptive_weights['extensibility'] +
            modularity_score * adaptive_weights['modularity'] +
            tech_debt_score * adaptive_weights['tech_debt_prevention']
        )

        return {
            'confidence_score': confidence_score,
            'risk_score': risk_score,
            'recommendation': recommendation,
            'adaptive_weights': adaptive_weights,
            'fingerprint': fingerprint.to_dict(),
            'reasoning_summary': reasoning_summary,
            'reasoning_factors': reasoning_factors,
            'mitigations': mitigations
        }
```

### Configuration

```python
class EvolutionSpecialistConfig(SpecialistConfig):

    # Evolution Hooks
    evolution_hooks_enabled: bool = True
    pattern_registry_collection: str = "evolution_pattern_registry"
    min_similar_patterns: int = 5
    weight_adjustment_max: float = 0.05
    feedback_consumer_enabled: bool = True
```

---

## Testing Strategy

### Test Structure

```
tests/evolution_hooks/
├── unit/
│   ├── test_fingerprint_extractor.py    # 15 testes
│   ├── test_pattern_matcher.py          # 20 testes
│   ├── test_weight_adapter.py           # 25 testes
│   └── test_pattern_registry.py         # 15 testes
│
├── integration/
│   ├── test_adaptive_evaluation.py      # 10 testes
│   └── test_feedback_loop.py            # 10 testes
│
└── e2e/
    └── test_evolution_hooks_e2e.py      # 5 testes
```

### Key Test Scenarios

1. **Cold Start** - Sem histórico, usa pesos default
2. **Learning** - Após N feedbacks, pesos convergem
3. **Overfitting Prevention** - Limita ajustes para evitar overfitting
4. **Conflicting Feedback** - Lida com feedbacks contraditórios
5. **Fallback** - Se MongoDB falha, usa heurísticas base

### E2E Scenarios

```python
def test_cold_start_to_learning():
    # 1. Avaliar plano sem histórico → pesos default
    # 2. Receber 10 feedbacks positivos
    # 3. Avaliar plano similar → pesos ajustados
    # 4. Verificar que pesos mudaram na direção correta

def test_pattern_decay():
    # 1. Criar padrão com 100% success rate
    # 2. Enviar 20 feedbacks negativos
    # 3. Verificar que pesos foram reajustados
```

---

## Deployment and Migration

### Feature Flag

```yaml
evolution_hooks:
  enabled: true
  rollout_percentage: 10  # Canary - 10% dos planos usam hooks
```

### Migration Script

```python
# m001_create_pattern_registry.py

def upgrade():
    """Criar índices para evolution_pattern_registry"""
    db.evolution_pattern_registry.create_index([
        ("fingerprint.domain", 1),
        ("fingerprint.complexity_signature", 1)
    ])
    db.evolution_pattern_registry.create_index([
        ("metrics.times_matched", -1)
    ])
```

### Kafka Topics

```
evolution.feedback.topic  (partitions: 3, replication: 2)
  ^ approval-service publishes
  ^ specialist-evolution consumes
```

### Rollback Plan

1. Se taxa de erro > 5% → disable evolution_hooks_enabled
2. Se latência > 500ms → disable evolution_hooks_enabled
3. Se success rate < baseline → rollback para pesos default

---

## Success Criteria

- [ ] Evolution Specialist pode ajustar pesos baseado em histórico
- [ ] Taxa de acerto aumenta após N feedbacks (validado em testes)
- [ ] Fallback para pesos default funciona quando MongoDB indisponível
- [ ] Feature flag permite canary deployment
- [ ] Todos os 95+ testes passando
- [ ] Documentação atualizada

---

## Next Steps

1. Criar spec detalhada de implementação
2. Implementar componentes core
3. Criar testes
4. Deploy canary (10%)
5. Monitorar e ajustar
6. Rollout gradual

---

**Document Version:** 1.0
**Last Updated:** 2026-03-24
