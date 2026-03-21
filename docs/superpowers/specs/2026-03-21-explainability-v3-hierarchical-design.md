# Explainability API v3 - Hierarchical Explainability Design

> **Created:** 2026-03-21
> **Status:** Design Approved
> **GAPS Reference:** Extensão de GAPS-04 + GAPS-03

---

## 1. Overview

A Explainability API v3 adiciona capacidades avançadas de explicação para decisões que utilizam **consenso hierárquico** (implementado em GAPS-03). A versão atual (v2) explica features mas não detalha como a senioridade dos especialistas influenciou a decisão final.

### Problema

Decisões tomadas via consenso hierárquico têm diferentes pesos por nível de senioridade (trainee=0.5x até expert=2.0x). A explainability atual não responde:

- Como o peso hierárquico afetou a decisão final?
- Qual especialista "puxou" a decisão para qual lado?
- E se os pesos fossem diferentes? (counterfactual)
- Como a influência evoluiu ao longo do tempo?

### Solução

Extender a Explainability API com:

1. **Hierarchical Explainer** - Breakdown por nível de senioridade
2. **Individual Contributions** - Ranking de influência por especialista
3. **Counterfactual Analyzer** - Análise "e se..." de cenários alternativos
4. **Temporal Tracker** - Evolução temporal e histórico de senioridade

---

## 2. Architecture

### Abordagem: Extension Service

Estender a API v2 existente sem quebrar código funcional.

```
explainability-api/
├── src/services/
│   ├── shap_calculator.py          # Existente (v2)
│   ├── quality_scorer.py           # Existente (v2)
│   ├── api_extensions.py           # Existente (v2)
│   ├── hierarchical_explainer.py   # NOVO - Core v3
│   ├── counterfactual_analyzer.py  # NOVO - Counterfactuals
│   └── temporal_tracker.py         # NOVO - Temporal analysis
├── src/repositories/
│   └── seniority_history_repo.py   # NOVO - Senioridade history
├── src/api/routes/
│   └── v3/                         # NOVOS endpoints v3
└── tests/
    ├── test_v3_hierarchical_explainer.py
    ├── test_v3_counterfactual_analyzer.py
    ├── test_v3_temporal_tracker.py
    ├── test_v3_seniority_history_repo.py
    ├── test_v3_api_endpoints.py
    └── test_v3_e2e_integration.py
```

---

## 3. Data Model

### Nova Coleção: `seniority_history`

```python
{
    "_id": ObjectId,
    "specialist_id": str,           # "business_analyst"
    "specialist_name": str,         # "Business Analyst"
    "domain": str,                  # "BUSINESS", "TECHNICAL", etc.
    "changed_at": datetime,         # Timestamp da mudança
    "previous_level": str,          # Nível anterior (ex: "mid_level")
    "previous_multiplier": float,   # Multiplicador anterior (ex: 1.0)
    "new_level": str,               # Novo nível (ex: "senior")
    "new_multiplier": float,        # Novo multiplicador (ex: 1.5)
    "changed_by": str,              # Quem fez a mudança
    "change_reason": str,           # Razão da mudança
    "decision_id": str,             # Contexto
    "plan_id": str                  # Contexto
}

# Indices
{"specialist_id": 1, "changed_at": -1}
{"domain": 1, "changed_at": -1}
{"changed_at": 1}
```

### Modelo de Resposta v3

```python
{
    "decision_id": str,
    "explainability_token": str,
    "generated_at": datetime,

    # === Novo: Breakdown por Senioridade ===
    "hierarchical_breakdown": {
        "by_level": {
            "expert": {
                "count": int,
                "weight_multiplier": float,
                "raw_votes": dict,
                "weighted_contribution": float,
                "influence_direction": str,  # "approve", "reject", "neutral"
                "specialists": list[str]
            },
            # ... senior, mid_level, junior, trainee
        },
        "dominant_level": str,
        "consensus_strength": float  # 0-1
    },

    # === Novo: Contribuicoes Individuais ===
    "individual_contributions": [
        {
            "specialist_id": str,
            "seniority_level": str,
            "multiplier": float,
            "vote": str,
            "confidence": float,
            "risk": float,
            "weighted_vote": str,
            "contribution_score": float,
            "rank": int
        },
        # ...
    ],

    # === Novo: Counterfactuals ===
    "counterfactuals": {
        "equal_weights_scenario": {...},
        "no_trainee_scenario": {...},
        "seniority_inversion": {...}
    },

    # === Novo: Analise Temporal ===
    "temporal_analysis": {
        "current_session": {...},
        "last_7_days": {...},
        "seniority_changes": [...]
    },

    # === Existente v2 ===
    "feature_attribution": dict,
    "quality_score": float,
    "shap_values": dict
}
```

---

## 4. API Endpoints

### Explicação Completa

```
GET /api/v3/explainability/{decision_id}
```

Retorna explicação completa v3.

### Explicação por Componente

```
GET /api/v3/explainability/{decision_id}/hierarchical
GET /api/v3/explainability/{decision_id}/individual
GET /api/v3/explainability/{decision_id}/counterfactuals
GET /api/v3/explainability/{decision_id}/temporal
```

### Filtros

```
GET /api/v3/explainability/{decision_id}?include=hierarchical,counterfactuals
GET /api/v3/explainability/{decision_id}?format=html
```

### Batch e Comparação

```
POST /api/v3/explainability/batch
```

Compara múltiplas decisões.

### Histórico de Senioridade

```
GET /api/v3/seniority/{specialist_id}/history
GET /api/v3/seniority/history?since=2026-03-01&domain=BUSINESS
```

---

## 5. Algoritmos

### Consensus Strength

Calcula quão unificado é o consenso entre níveis hierárquicos (0-1).

```
1. Extrair direção de cada nível (+1 approve, -1 reject, 0 neutral)
2. Se todos apontam mesma direção → 1.0
3. Se divididos → proporção de níveis na direção dominante
```

### Counterfactual Scenarios

Três cenários padrão:

1. **Equal Weights** - Todos com peso 1.0x
2. **No Trainee** - Ignorar opiniões de Trainee
3. **Seniority Inversion** - Inverter multiplicadores (expert=0.5, trainee=2.0)

### Temporal Tracking

Três níveis de análise:

1. **Current Session** - Decisões no mesmo workflow
2. **Time Window** - Últimos 7 dias, 30 dias
3. **Seniority Changes** - Histórico de mudanças de nível

---

## 6. Testing

### Cobertura Esperada: ~100 testes

| Componente | Unitários | Integração | Total |
|------------|-----------|------------|-------|
| HierarchicalExplainer | 12-15 | 5 | ~20 |
| CounterfactualAnalyzer | 10-12 | 4 | ~15 |
| TemporalTracker | 8-10 | 6 | ~15 |
| SeniorityHistoryRepository | 6-8 | 4 | ~12 |
| API Endpoints v3 | 15-18 | 6 | ~25 |
| E2E | - | 8-10 | ~10 |

### Casos de Teste Chave

- Breakdown com opiniões de único nível
- Breakdown com níveis mistos
- Consensus strength unânime vs dividido
- Counterfactual que inverte decisão
- Análise temporal com mudança de senioridade
- E2E completo com todos os componentes

---

## 7. Metrics & Observability

### Métricas Prometheus

- `v3_generation_duration_seconds` - Tempo por componente
- `v3_explanations_total` - Total gerado por formato
- `consensus_strength` - Distribuição por nível dominante
- `dominant_level_total` - Contagem por nível
- `counterfactual_outcome_total` - Resultado de cenários
- `temporal_cache_hits_total` - Cache hit rate
- `seniority_changes` - Mudanças por especialista

### Logs Estruturados

- `v3_explanation_generated` - Geração completa
- `counterfactual_analysis_completed` - Análise counterfactual
- `temporal_analysis_retrieved` - Análise temporal
- `low_consensus_strength` - Alerta de consenso fraco

---

## 8. Deployment Plan

| Fase | Componentes | Risco | Rollback |
|------|-------------|-------|----------|
| 1 | MongoDB migration (seniority_history) | Baixo | Drop collection |
| 2 | Repositories e Services (backend) | Baixo | Feature flag |
| 3 | API v3 endpoints (shadow mode) | Médio | Desabilitar v3 |
| 4 | Produção completa (v3 ativo) | Médio | Redirect para v2 |

### Feature Flags

```bash
ENABLE_V3_HIERARCHICAL_EXPLAINABILITY=true
V3_SHADOW_MODE=true  # Inicialmente true, depois false
```

---

## 9. Dependencies

### Internas

- `consensus-engine` - GAPS-03 (seniority models)
- `explainability-api` v2 - SHAP, QualityScorer
- `neural_hive_specialists` - BaseSpecialist, behaviours

### Externas

- MongoDB 5.0+ (nova coleção)
- Kafka (tópicos existentes)
- Prometheus (métricas)

---

## 10. Success Criteria

- [ ] 100% dos testes passando
- [ ] Consensus strength calculado corretamente
- [ ] Counterfactuals gerados para 3+ cenários
- [ ] Temporal analysis funcionando para 7d/30d
- [ ] API v3 respondendo <500ms (p95)
- [ ] Zero regressão em v2
- [ ] Documentação atualizada

---

## 11. Data Sources

### Fonte de Dados para v3

```python
# specialist_votes com campos hierarquicos (GAPS-03)
specialist_votes = [
    {
        "specialist_id": "business_expert",
        "specialist_name": "Business Expert",
        "domain": "BUSINESS",
        "seniority_level": "expert",        # GAPS-03
        "seniority_multiplier": 2.0,        # GAPS-03
        "vote": "approve",
        "confidence": 0.92,
        "risk": 0.15,
        "opinion": {...}
    },
    # ...
]

# Fonte: consensus_engine -> ConsolidatedDecision -> specialist_votes
# Armazenado em: MongoDB colecao `consensus_decisions`
```

### Comportamento para Legado (pré-GAPS-03)

Se `seniority_level` é `None`:
- Usar `mid_level` (1.0x) como default
- Log warning: `"legacy_decision_no_seniority"`
- Retornar campos hierarquicos com valores padrão

### Bug Fix Pré-requisito

**Issue:** `ReasoningExtractor` é importado mas não existe.

**Solução:** Criar `src/services/reasoning_extractor.py` ou remover import.

**Decisão:** Criar stub vazio para não quebrar v2.

---

## 12. MongoDB Migration

### Script: `m004_seniority_history.py`

```python
# Migration para criar colecao seniority_history
async def upgrade():
    await db.create_collection("seniority_history")
    await db.seniority_history.create_index([("specialist_id", 1), ("changed_at", -1)])
    await db.seniority_history.create_index([("domain", 1), ("changed_at", -1)])
    await db.seniority_history.create_index([("changed_at", 1)])

# Backfill: ler mudancas de logs de auditoria se disponiveis
# Se nao: colecao inicia vazia, populada em tempo real
```

---

## 13. Algorithms - Pseudo-Code

### Consensus Strength (Fórmula Exata)

```
function calculate_consensus_strength(by_level):
    directions = []
    for level_data in by_level.values():
        contribution = level_data['weighted_contribution']
        if contribution > 0:
            directions.append(+1)  # approve
        elif contribution < 0:
            directions.append(-1)  # reject
        else:
            directions.append(0)   # neutral

    if not directions:
        return 0.0

    # Se todos concordam
    if all(d == directions[0] for d in directions):
        return 1.0

    # Proporção na direção dominante
    dominant = directions[0]
    same_direction_count = sum(1 for d in directions if d == dominant)
    return same_direction_count / len(directions)
```

**Edge cases:**
- 2 approve, 2 reject → 0.5 (50% concordância)
- 1 approve, 1 reject, 1 neutral → 0.33 (33% concordância)

### Counterfactual Analyzer (Implementação)

```
function generate_counterfactuals(original_decision, votes):
    scenarios = []

    # 1. Equal Weights
    equal_votes = [{**v, "seniority_multiplier": 1.0} for v in votes]
    equal_result = consensus_orchestrator.consolidate(equal_votes)
    scenarios.append({
        "name": "equal_weights_scenario",
        "result": compare(original_decision, equal_result)
    })

    # 2. No Trainee
    no_trainee_votes = [v for v in votes if v["seniority_level"] != "trainee"]
    if no_trainee_votes:
        no_trainee_result = consensus_orchestrator.consolidate(no_trainee_votes)
        scenarios.append({...})

    # 3. Seniority Inversion
    inverted_multipliers = {
        "expert": 0.5, "senior": 0.75, "mid_level": 1.0,
        "junior": 1.5, "trainee": 2.0
    }
    inverted_votes = [
        {**v, "seniority_multiplier": inverted_multipliers[v["seniority_level"]]}
        for v in votes
    ]
    inverted_result = consensus_orchestrator.consolidate(inverted_votes)
    scenarios.append({...})

    return scenarios
```

### Temporal Tracker (Fonte de Dados)

```
function get_temporal_analysis(decision_id):
    # 1. Current Session
    # Fonte: MongoDB colecao `consensus_decisions`
    # Query: {"plan_id": decision.plan_id, "created_at": {$gte: session_start}}

    # 2. Last 7 Days
    # Fonte: MongoDB colecao `consensus_decisions`
    # Query: {"created_at": {$gte: now() - 7days}}

    # 3. Seniority Changes
    # Fonte: MongoDB colecao `seniority_history` (NOVA)
    # Query: {"specialist_id": {$in: involved_specialists}, "changed_at": {$gte: now() - 30days}}
```

---

## 14. Edge Cases - Test Coverage

Casos adicionais a testar:

| Caso | Comportamento Esperado |
|------|----------------------|
| Decisão sem `seniority_level` | Usar `mid_level` default, log warning |
| `seniority_level` inválido | Erro 400 com lista de valores válidos |
| Single opinion (1 especialista) | Consensus strength = 1.0 |
| Counterfactual com única opinião | Retornar single scenario |
| Temporal window vazia | Retornar `{}` com status "no_data" |
| Decisões pré-GAPS-03 | Valores default hierárquicos |

---

## 15. Batch Endpoint - Schema

```python
# POST /api/v3/explainability/batch
class BatchExplanationRequest(BaseModel):
    decision_ids: List[str]  # Max 50
    include: List[str] = ["hierarchical", "temporal"]
    comparison_mode: str = "trend"  # trend, distribution, both

class BatchExplanationResponse(BaseModel):
    decisions: Dict[str, HierarchicalExplanation]
    comparison: BatchComparison
    metadata: {
        "total": int,
        "successful": int,
        "failed": int,
        "processing_time_ms": int
    }
```

---

## 16. Version Coexistence

v2 e v3 coexistem durante rollout:

```
Phase 2 (Shadow Mode):
- /api/v2/* - ativo, serve tráfego real
- /api/v3/* - disponível mas não publicado no gateway
- Feature flag: ENABLE_V3_SHADOW_MODE=true

Phase 3 (Canary):
- /api/v2/* - 80% tráfego
- /api/v3/* - 20% tráfego (via load balancer)
- Feature flag: ENABLE_V3_CANARY=true

Phase 4 (Full):
- /api/v2/* - deprecado, redirect para /api/v3/*
- /api/v3/* - 100% tráfego
- Feature flag: ENABLE_V3=true, V2_REDIRECT=true
```

---

## 17. Prerequisites

### Bug Fix: ReasoningExtractor

**Issue:** `main.py:36,38,98` importa `ReasoningExtractor` mas o arquivo não existe.

**Task 0: Criar ReasoningExtractor Stub**

```python
# services/explainability-api/src/services/reasoning_extractor.py

from typing import Dict, Any, List

class ReasoningExtractor:
    """
    Extrai fatores de raciocínio de opiniões de especialistas.

    Stub implementado para v3 - expandir em iteração futura.
    """

    def extract_reasoning_factors(self, opinion: Dict[str, Any]) -> List[str]:
        """Extrai fatores de raciocínio de uma opinião."""
        # Stub: retorna lista vazia por enquanto
        return []

    def extract_from_text(self, text: str) -> List[str]:
        """Extrai fatores de texto livre."""
        # Stub: implementação futura com NLP
        return []
```

**Testes:**

```python
# tests/test_reasoning_extractor.py

def test_reasoning_extractor_init():
    extractor = ReasoningExtractor()
    assert extractor is not None

def test_extract_reasoning_factors_stub():
    extractor = ReasoningExtractor()
    factors = extractor.extract_reasoning_factors({"opinion": "test"})
    assert factors == []  # Stub retorna vazio
```

---

## 18. Open Questions

Nenhuma - design completo e aprovado (após revisão).

---

## 19. References

- GAPS-03: Consenso Hierárquico (5 níveis, 132 testes)
- GAPS-04: Explainability API v2 (SHAP, QualityScorer, 66 testes)
- Consensus Engine: `/services/consensus-engine/src/models/seniority.py`
- Explainability API: `/services/explainability-api/src/main.py`
