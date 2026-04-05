# EPIC-202: A/B Testing Persistência

**ID:** EPIC-202
**Status:** Pending
**Priority:** P1 - Alta
**Effort:** M (2 semanas)
**Related Service:** optimizer-agents

---

## Resumo Executivo

Implementar persistência de resultados de A/B testing no MongoDB. O engine está 100% completo com análise estatística, mas os resultados (`ABTestResults`) não são salvos permanentemente - apenas retornados em memória. Completude atual: 70% (engine completo, falta persistência).

---

## Análise Técnica

### O que Existe (100%)

| Componente | Arquivo | Linhas | Status |
|------------|---------|--------|--------|
| `ABTestingEngine` | ab_testing_engine.py | 881 | ✅ Completo |
| `StatisticalAnalyzer` | statistical_analysis.py | 528 | ✅ Completo |
| `SampleSizeCalculator` | sample_size_calculator.py | 383 | ✅ Completo |
| `GuardrailMonitor` | guardrails.py | 404 | ✅ Completo |
| APIs REST | ab_testing.py | 412 | ✅ Completo |

### O que Falta (0%)

| Componente | Descrição | Status |
|------------|-----------|--------|
| `save_ab_test_results()` | Método para persistir resultados | ❌ Não existe |
| `ab_test_results` collection | Coleção MongoDB para resultados | ❌ Não existe |
| Migration script | Criar índices da coleção | ❌ Não existe |
| `get_ab_test_history()` | Recuperar histórico | ❌ Não existe |

### Fluxo Atual vs Desejado

```python
# ATUAL (sem persistência)
results = await ab_engine.analyze_results(experiment_id)
return results  # ← Apenas retorna, não salva

# DESEJADO (com persistência)
results = await ab_engine.analyze_results(experiment_id)
await mongo_client.save_ab_test_results(results)  # ← PERSISTE
return results
```

---

## Ticket EPIC-202-01: Criar Coleção MongoDB

**ID:** TICKET-EPIC-202-01
**Priority:** Alta
**Effort:** S (2 dias)

### Tasks

- [ ] 202.01 Criar `src/database/migrations/m002_ab_test_results.py`
- [ ] 202.02 Definir schema da coleção `ab_test_results`
- [ ] 202.03 Criar índices: experiment_id, created_at, status
- [ ] 202.04 Criar índices compostos: status+created_at
- [ ] 202.05 Criar índices: statistical_recommendation
- [ ] 202.06 Adicionar script de rollback
- [ ] 202.07 Testar migration localmente
- [ ] 202.08 Validar índices criados

### Schema MongoDB

```javascript
// Coleção: ab_test_results
{
  _id: ObjectId,
  experiment_id: "uuid-v4",
  experiment_name: "string",
  
  // Timestamps
  created_at: ISODate,
  completed_at: ISODate,
  analysis_timestamp: ISODate,
  
  // Status
  status: "running|completed|aborted",
  
  // Tamanhos de amostra
  control_size: Int32,
  treatment_size: Int32,
  
  // Métricas primárias
  primary_metrics_analysis: [
    {
      metric_name: "latency_p95",
      test_used: "welch_t_test",
      p_value: 0.001,
      statistically_significant: true,
      effect_size: 0.45,
      control_mean: 150.5,
      treatment_mean: 82.3,
      confidence_interval_95: [50.2, 86.4]
    }
  ],
  
  // Análise Bayesiana
  bayesian_analysis: [...],
  
  // Guardrails
  guardrails_status: {
    violated: false,
    should_abort: false
  },
  
  // Decisão
  statistical_recommendation: "APPLY|REJECT|INCONCLUSIVE",
  confidence_level: 0.95
}
```

### Índices

```javascript
db.ab_test_results.createIndex({ experiment_id: 1 }, { unique: true })
db.ab_test_results.createIndex({ created_at: -1 })
db.ab_test_results.createIndex({ status: 1, created_at: -1 })
db.ab_test_results.createIndex({ statistical_recommendation: 1 })
```

### Critérios de Aceite
- [ ] Migration criada
- [ ] Schema validado
- [ ] Índices criados corretamente
- [ ] Migration testada

---

## Ticket EPIC-202-02: Adicionar Métodos MongoDB Client

**ID:** TICKET-EPIC-202-02
**Priority:** Alta
**Effort:** M (4 dias)

### Tasks

- [ ] 202.09 Modificar `src/clients/mongodb_client.py`
- [ ] 202.10 Implementar `save_ab_test_results(results)`
- [ ] 202.11 Implementar `get_ab_test_results(experiment_id)`
- [ ] 202.12 Implementar `list_ab_test_results(filters, limit)`
- [ ] 202.13 Implementar `get_ab_test_history(days)`
- [ ] 202.14 Implementar `get_ab_test_aggregations(metric_name, days)`
- [ ] 202.15 Criar `src/models/ab_test_results_persistent.py`
- [ ] 202.16 Implementar `ABTestResultsPersistent` model
- [ ] 202.17 Adicionar testes dos novos métodos
- [ ] 202.18 Testar persistência de resultados

### Métodos a Implementar

```python
class MongoDBClient:
    async def save_ab_test_results(
        self, 
        results: ABTestResults
    ) -> str:
        """Salvar resultados no MongoDB.
        
        Returns:
            str: ID do documento inserido
        """
        doc = {
            "experiment_id": results.experiment_id,
            "experiment_name": results.experiment_name,
            "created_at": datetime.now(timezone.utc),
            "completed_at": datetime.now(timezone.utc),
            "status": results.status,
            # ... mapear todos os campos
        }
        
        result = await self.db.ab_test_results.insert_one(doc)
        return str(result.inserted_id)

    async def get_ab_test_results(
        self, 
        experiment_id: str
    ) -> Optional[Dict]:
        """Recuperar resultados por experiment_id."""
        return await self.db.ab_test_results.find_one(
            {"experiment_id": experiment_id}
        )

    async def list_ab_test_results(
        self,
        filters: Optional[Dict] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Listar resultados com filtros."""
        query = filters or {}
        cursor = self.db.ab_test_results.find(query).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_ab_test_history(
        self,
        experiment_id: str,
        days: int = 30
    ) -> List[Dict]:
        """Histórico de snapshots de um experimento."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        return await self.db.ab_test_results.find({
            "experiment_id": experiment_id,
            "created_at": {"$gte": since}
        }).to_list(None)
```

### Critérios de Aceite
- [ ] Métodos implementados
- [ ] ABTestResultsPersistent model criado
- [ ] Testes passando
- [ ] Persistência validada

---

## Ticket EPIC-202-03: Integrar Persistência no Engine

**ID:** TICKET-EPIC-202-03
**Priority:** Alta
**Effort:** M (3 dias)

### Tasks

- [ ] 202.19 Modificar `src/experimentation/ab_testing_engine.py`
- [ ] 202.20 Modificar `analyze_results()` para persistir
- [ ] 202.21 Modificar `src/services/experiment_manager.py`
- [ ] 202.22 Modificar `analyze_experiment_results()` para persistir
- [ ] 202.23 Modificar `src/api/ab_testing.py`
- [ ] 202.24 Adicionar endpoint `GET /api/v1/ab-tests/{id}/results`
- [ ] 202.25 Adicionar endpoint `GET /api/v1/ab-tests/history`
- [ ] 202.26 Adicionar endpoint `GET /api/v1/ab-tests/aggregations`
- [ ] 202.27 Testar fluxo completo: criar → analisar → persistir → recuperar
- [ ] 202.28 Testar endpoint de histórico

### Fluxo Completo

```python
# No ABTestingEngine
async def analyze_results(self, experiment_id: str) -> ABTestResults:
    # ... análise estatística completa ...
    results = ABTestResults(...)
    
    # NOVO: Persistir resultados
    results_id = await self.mongo_client.save_ab_test_results(results)
    logger.info(f"Results persisted with ID: {results_id}")
    
    return results

# No ExperimentManager
async def analyze_experiment_results(self, experiment_id: str) -> Dict:
    ab_results = await self.ab_testing_engine.analyze_results(experiment_id)
    
    # NOVO: Recuperar resultado persistido para validação
    persisted = await self.mongo_client.get_ab_test_results(experiment_id)
    assert persisted is not None
    
    return {
        "results": ab_results,
        "persisted_id": persisted["_id"],
        "persisted_at": persisted["created_at"]
    }
```

### Critérios de Aceite
- [ ] Engine persiste resultados após análise
- [ ] ExperimentManager valida persistência
- [ ] Endpoints novos funcionando
- [ ] Histórico recuperável

---

## Ticket EPIC-202-04: Dashboard de A/B Testing

**ID:** TICKET-EPIC-202-04
**Priority:** Média
**Effort:** S (3 dias)

### Tasks

- [ ] 202.29 Criar endpoint `GET /api/v1/ab-tests/dashboard`
- [ ] 202.30 Implementar agregações: win rate, avg lift
- [ ] 202.31 Implementar filtros: data range, metric
- [ ] 202.32 Criar dashboard frontend (opcional)
- [ ] 202.33 Testar dashboard com dados reais

### Endpoint Dashboard

```python
# GET /api/v1/ab-tests/dashboard?days=30
{
    "period": {"days": 30, "from": "2026-03-01", "to": "2026-03-31"},
    "total_experiments": 15,
    "completed_experiments": 12,
    "win_rate": 0.67,  # % de experimentos onde treatment venceu
    "avg_lift": 0.23,   # lift médio
    "statistical_power": 0.85,
    "top_experiments": [
        {"experiment_id": "xxx", "lift": 0.45, "p_value": 0.001},
        {"experiment_id": "yyy", "lift": 0.32, "p_value": 0.005}
    ],
    "metric_breakdown": {
        "latency_p95": {"avg_lift": 0.15, "experiments": 8},
        "throughput": {"avg_lift": 0.35, "experiments": 6},
        "error_rate": {"avg_lift": -0.20, "experiments": 4}
    }
}
```

### Critérios de Aceite
- [ ] Endpoint dashboard funcionando
- [ ] Agregações corretas
- [ ] Filtros funcionando

---

## Resumo do Epic

| Ticket | Descrição | Effort | Deliverables |
|--------|-----------|--------|--------------|
| EPIC-202-01 | Criar coleção MongoDB | 2 dias | Migration + índices |
| EPIC-202-02 | Métodos MongoDB Client | 4 dias | 4 métodos |
| EPIC-202-03 | Integração no Engine | 3 dias | Engine + API |
| EPIC-202-04 | Dashboard | 3 dias | Endpoint dashboard |
| **TOTAL** | | **2 semanas** | **Persistência completa** |

---

## Arquitetura Final

```
                    ┌─────────────────────────────────────┐
                    │            API Layer                │
                    │  POST /api/v1/ab-testing/{id}/results│
                    │  GET  /api/v1/ab-tests/{id}/history ││
                    │  GET  /api/v1/ab-tests/dashboard    ││
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │        ExperimentManager             │
                    │  - analyze_experiment_results()     │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │         ABTestingEngine             │
                    │  - analyze_results()                │
                    │  - + persiste resultados            │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │          MongoDBClient               │
                    │  - save_ab_test_results()  NOVO     │
                    │  - get_ab_test_results()   NOVO     │
                    │  - list_ab_test_results()  NOVO     │
                    │  - get_ab_test_history()    NOVO     │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │       MongoDB ab_test_results       │
                    │       (NOVA coleção)                │
                    └─────────────────────────────────────┘
```

---

## Handoff para Claude Code

```
@~/.agent-os/instructions/execute-tasks.md

Epic: EPIC-202 - A/B Testing Persistência
Spec: .agent-os/specs/2026-03-31-sprint2-features-incompletas/
```
