# Evolution Hooks - Meta-Learning Design Document

**Project:** Neural-Hive-Mind
**Component:** Evolution Specialist - Evolution Hooks
**Date:** 2026-03-24
**Status:** Design v1.1 (Revised)
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
3. **WeightAdapter** - Ajusta pesos baseado em histórico de planos similares
4. **FeedbackConsumer** - Consome feedback do Approval Service e atualiza o registry

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
    2. Similaridade Jaccard em task_types
    3. Proximidade em task_count_range e complexity_signature

    Similaridade Jaccard = |A ∩ B| / |A ∪ B|
    onde A e B são conjuntos de task_types
    """
    query = {
        "fingerprint.domain": fingerprint["domain"],
        "fingerprint.complexity_signature": {
            "$regex": f"^{fingerprint['complexity_signature'][:3]}"
        }
    }

    candidates = db.pattern_registry.find(query).to_list(None)

    # Calcular similaridade Jaccard e ordenar
    for candidate in candidates:
        jaccard = calculate_jaccard(
            fingerprint["task_types"],
            candidate["fingerprint"]["task_types"]
        )
        candidate["_similarity_score"] = jaccard

    return sorted(candidates, key="_similarity_score", reverse=True)[:limit]
```

### Weight Adjustment

Para planos similares com histórico de sucesso:
- Se `maintainability` foi consistente nos sucessos → aumenta peso (max +0.05)
- Se `tech_debt_prevention` teve alta correlação com rejects → diminui peso (max -0.05)

---

## Default Weights (Alinhado com Código Atual)

```python
DEFAULT_WEIGHTS = {
    "maintainability": 0.25,      # 25%
    "scalability": 0.25,          # 25%
    "extensibility": 0.20,        # 20%
    "modularity": 0.15,           # 15%
    "tech_debt_prevention": 0.15  # 15%
}
```

**Nota:** Estes são os mesmos pesos usados atualmente em `EvolutionSpecialist._evaluate_plan_internal()` (linhas 132-138 do specialist.py).

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

### Kafka Message Schema

**Topic:** `evolution.feedback.topic`
**Schema (Avro/JSON):**

```json
{
  "plan_id": "uuid",
  "fingerprint": {
    "domain": "technical",
    "priority": "high",
    "task_count_range": "medium",
    "task_types": ["BUILD", "TEST", "DEPLOY"],
    "avg_dependency_count": 1.5,
    "has_conditional_deps": true,
    "complexity_signature": "M-S-T-H-M"
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
    }
  },
  "feedback": {
    "outcome": "approve",          # "approve" ou "reject"
    "source": "human",             # "human", "automated", "system"
    "reasoning": "Plano aprovado após revisão",
    "timestamp": "2026-03-24T10:00:00Z"
  }
}
```

**Publisher (Approval Service):**

O Approval Service deve publicar feedback após decisão final. A mensagem inclui o fingerprint e os pesos que foram usados na avaliação original.

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
    reasoning: String,
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
│   ├── pattern_registry.py         # Repository MongoDB
│   ├── models.py                   # Pydantic models
│   └── feedback_consumer.py        # Consome feedback do Kafka
```

**Nota:** Seguindo o padrão existing de `feedback/`, todos os componentes ficam no mesmo diretório.

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

# pattern_registry.py
class PatternRegistry:
    def store_evaluation(self, fingerprint, evaluation, feedback):
        """Armazena avaliação com fingerprint"""

    def get_similar_patterns(self, fingerprint, limit):
        """Busca padrões similares"""

# feedback_consumer.py
class EvolutionFeedbackConsumer:
    async def consume(self):
        """Consome mensagens do Kafka e atualiza registry"""
```

---

## Integration with Evolution Specialist

### Modified Evaluation Flow

```python
# services/specialist-evolution/src/specialist.py

class EvolutionSpecialist(BaseSpecialist):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Novos componentes de evolution hooks
        self.fingerprint_extractor = FingerprintExtractor()
        self.pattern_matcher = PatternMatcher(self.mongo_client)
        self.weight_adapter = WeightAdapter(self.pattern_matcher)

    def _evaluate_plan_internal(self, cognitive_plan, context):
        """
        Avaliação com meta-learning:
        1. Extrair fingerprint do plano
        2. Buscar padrões similares e ajustar pesos
        3. Usar pesos adaptados no cálculo final
        4. Retornar opinião com metadados de evolution
        """
        # 1. Extrair fingerprint
        fingerprint = self.fingerprint_extractor.extract(cognitive_plan)

        # 2. Buscar padrões similares e ajustar pesos
        adaptive_weights = self.weight_adapter.adapt_weights(fingerprint)

        # 3. Análises individuais (sem mudanças)
        maintainability_score = self._analyze_maintainability(tasks, cognitive_plan)
        scalability_score = self._analyze_scalability(tasks, cognitive_plan)
        extensibility_score = self._analyze_extensibility(tasks, cognitive_plan)
        modularity_score = self._analyze_modularity(tasks)
        tech_debt_score = self._analyze_tech_debt_risk(tasks, cognitive_plan)

        # 4. Calcular scores agregados com pesos adaptativos
        confidence_score = (
            maintainability_score * adaptive_weights['maintainability'] +
            scalability_score * adaptive_weights['scalability'] +
            extensibility_score * adaptive_weights['extensibility'] +
            modularity_score * adaptive_weights['modularity'] +
            tech_debt_score * adaptive_weights['tech_debt_prevention']
        )

        # Calcular risco
        risk_score = self._calculate_evolution_risk(
            maintainability_score, scalability_score, extensibility_score,
            modularity_score, tech_debt_score
        )

        # Determinar recomendação
        recommendation = self._determine_recommendation(confidence_score, risk_score)

        # Gerar justificativa
        reasoning_summary = self._generate_reasoning(
            maintainability_score, scalability_score, extensibility_score,
            modularity_score, tech_debt_score, recommendation
        )

        # Fatores de raciocínio
        reasoning_factors = [
            {
                'factor_name': 'maintainability',
                'weight': adaptive_weights['maintainability'],
                'score': maintainability_score,
                'description': 'Facilidade de manutenção baseada em clareza, acoplamento e coesão'
            },
            {
                'factor_name': 'scalability',
                'weight': adaptive_weights['scalability'],
                'score': scalability_score,
                'description': 'Capacidade de escalar horizontal e verticalmente'
            },
            {
                'factor_name': 'extensibility',
                'weight': adaptive_weights['extensibility'],
                'score': extensibility_score,
                'description': 'Facilidade de adicionar novos recursos no futuro'
            },
            {
                'factor_name': 'modularity',
                'weight': adaptive_weights['modularity'],
                'score': modularity_score,
                'description': 'Design modular e separação de responsabilidades'
            },
            {
                'factor_name': 'tech_debt_prevention',
                'weight': adaptive_weights['tech_debt_prevention'],
                'score': tech_debt_score,
                'description': 'Prevenção de débito técnico futuro'
            }
        ]

        # Sugestões de mitigação
        mitigations = self._generate_mitigations(
            maintainability_score, scalability_score, extensibility_score,
            modularity_score, tech_debt_score
        )

        # Armazenar avaliação para futuro learning (async)
        if self.config.evolution_hooks_enabled:
            self._store_evaluation_async(fingerprint, adaptive_weights, {
                'confidence_score': confidence_score,
                'risk_score': risk_score,
                'recommendation': recommendation,
                'reasoning_factors': reasoning_factors
            })

        return {
            'confidence_score': confidence_score,
            'risk_score': risk_score,
            'recommendation': recommendation,
            'reasoning_summary': reasoning_summary,
            'reasoning_factors': reasoning_factors,
            'mitigations': mitigations,
            'metadata': {
                'maintainability_score': maintainability_score,
                'scalability_score': scalability_score,
                'extensibility_score': extensibility_score,
                'modularity_score': modularity_score,
                'tech_debt_score': tech_debt_score,
                'domain': domain,
                'priority': priority,
                'num_tasks': len(tasks),
                # Meta-learning metadata
                'adaptive_weights': adaptive_weights,
                'fingerprint': fingerprint.to_dict(),
                'learning_enabled': True
            }
        }

    def _store_evaluation_async(self, fingerprint, weights, evaluation):
        """Armazena avaliação no pattern registry (async, non-blocking)"""
        # Implementação com asyncio.create_task ou background thread
        pass
```

### Configuration

```python
# services/specialist-evolution/src/config.py

class EvolutionSpecialistConfig(SpecialistConfig):
    """Configuração do Evolution Specialist."""

    # Override defaults (existentes)
    specialist_type: str = "evolution"
    service_name: str = "specialist-evolution"
    mlflow_experiment_name: str = "evolution-specialist"
    mlflow_model_name: str = "evolution-evaluator"

    # Domínios suportados (existentes)
    supported_domains: List[str] = [
        "maintainability-analysis",
        "scalability-evaluation",
        "extensibility-design",
        "tech-debt-assessment",
        "architectural-evolution"
    ]

    # Configurações específicas (existentes)
    maintainability_enabled: bool = True
    scalability_analysis_enabled: bool = True
    tech_debt_threshold_high: float = 0.7
    tech_debt_threshold_low: float = 0.3

    # ========== Evolution Hooks (NOVOS) ==========
    evolution_hooks_enabled: bool = True
    pattern_registry_collection: str = "evolution_pattern_registry"
    min_similar_patterns: int = 5
    weight_adjustment_max: float = 0.05
    feedback_consumer_enabled: bool = True
    kafka_feedback_topic: str = "evolution.feedback.topic"
```

---

## Testing Strategy

### Test Structure

```
libraries/python/neural_hive_specialists/tests/evolution_hooks/
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
    """
    Cenário: Cold Start → Learning
    1. Avaliar plano sem histórico → pesos default
    2. Receber 10 feedbacks positivos
    3. Avaliar plano similar → pesos ajustados
    4. Verificar que pesos mudaram na direção correta
    """
    # Given: Plano técnico de complexidade média
    plan = create_test_plan(domain="technical", complexity="medium")

    # When: Primeira avaliação (cold start)
    result1 = specialist.evaluate_plan(plan)
    assert result1['adaptive_weights'] == DEFAULT_WEIGHTS

    # When: 10 feedbacks positivos
    for _ in range(10):
        publish_feedback(plan_id=plan.id, outcome="approve")

    # Then: Segunda avaliação com pesos ajustados
    result2 = specialist.evaluate_plan(plan)
    assert result2['adaptive_weights']['maintainability'] > 0.25

def test_pattern_decay():
    """
    Cenário: Pattern Decay
    1. Criar padrão com 100% success rate
    2. Enviar 20 feedbacks negativos
    3. Verificar que pesos foram reajustados
    """
    # Given: Padrão estabelecido com alta success rate
    pattern = create_established_pattern(success_rate=1.0)

    # When: 20 feedbacks negativos
    for _ in range(20):
        publish_feedback(pattern_id=pattern.id, outcome="reject")

    # Then: Pesos reajustados
    similar = find_similar(pattern.fingerprint)
    assert similar[0]['metrics']['success_rate'] < 0.5
```

---

## Deployment and Migration

### Feature Flag

```yaml
# evolution-harness.yaml ou config
evolution_hooks:
  enabled: true
  rollout_percentage: 10  # Canary - 10% dos planos usam hooks
  max_updates_per_second: 100  # Rate limiting no consumer
```

### Migration Path

#### Phase 1: Schema Creation

```python
# libraries/python/neural_hive_specialists/evolution_hooks/migrations/
# m001_create_pattern_registry.py

def upgrade():
    """Criar coleção e índices para evolution_pattern_registry"""
    db = client.get_database()

    # Criar coleção
    db.create_collection("evolution_pattern_registry")

    # Criar índices
    db.evolution_pattern_registry.create_index([
        ("fingerprint.domain", 1),
        ("fingerprint.complexity_signature", 1)
    ])

    db.evolution_pattern_registry.create_index([
        ("metrics.times_matched", -1)
    ])

    db.evolution_pattern_registry.create_index([
        ("created_at", 1)
    ], expireAfterSeconds=7776000)  # 90 dias TTL
```

#### Phase 2: Backfill (Opcional)

```python
# m002_backfill_historical_patterns.py

def upgrade():
    """
    Backfill de avaliações históricas do Evolution Specialist.
    Extrai fingerprints de avaliações passadas e popula o registry.
    """
    # Buscar avaliações dos últimos 30 dias
    historical_evaluations = db.specialist_evaluations.find({
        "specialist_type": "evolution",
        "created_at": {"$gte": datetime.now() - timedelta(days=30)}
    })

    for eval in historical_evaluations:
        fingerprint = extract_fingerprint_from_evaluation(eval)
        store_pattern(fingerprint, eval)
```

#### Phase 3: Kafka Topic Setup

```bash
# Criar tópico Kafka
kafka-topics.sh --create \
  --topic evolution.feedback.topic \
  --partitions 3 \
  --replication-factor 2 \
  --bootstrap-server ${KAFKA_BOOTSTRAP_SERVERS}
```

### Kafka Topics

```
evolution.feedback.topic  (partitions: 3, replication: 2)
  ^ approval-service publishes (via EvolutionFeedbackProducer)
  ^ specialist-evolution consumes (via EvolutionFeedbackConsumer)
```

### Rollback Plan

1. Se taxa de erro > 5% → set `evolution_hooks_enabled: false`
2. Se latência > 500ms → set `evolution_hooks_enabled: false`
3. Se success rate < baseline → rollback para pesos default
4. Se Kafka consumer failing → consumer para, pesos continuam funcionando

---

## Success Metrics

### Technical Metrics

- [ ] Evolution Specialist pode ajustar pesos baseado em histórico
- [ ] Fallback para pesos default funciona quando MongoDB indisponível
- [ ] Feature flag permite canary deployment
- [ ] Rate limiting no consumer funciona corretamente

### Quality Metrics

- [ ] Todos os 95+ testes passando
- [ ] Taxa de acerto aumenta após N feedbacks (validado em testes)
- [ ] Latência adicional < 100ms por avaliação
- [ ] Documentação atualizada

### Learning Metrics

- [ ] `adaptation_rate`: % de avaliações que usam pesos adaptados
- [ ] `accuracy_improvement_over_baseline`: diferença de accuracy
- [ ] `pattern_match_rate`: % de avaliações com matches similares

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

1. Criar spec detalhada de implementação (Agent OS spec)
2. Implementar componentes core
3. Criar testes
4. Deploy canary (10%)
5. Monitorar e ajustar
6. Rollout gradual

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-24 | Initial design |
| 1.1 | 2026-03-24 | Fixed issues: aligned default weights with code, corrected directory structure, added Kafka message schema, standardized field names, added Jaccard similarity details, added migration path |

---

**Document Version:** 1.1
**Last Updated:** 2026-03-24
