# Spec: INFRA-011 - LoadPredictor Integration

**Epic:** Integração do LoadPredictor no Fluxo de Enriquecimento
**Data:** 2026-04-14
**Prioridade:** P0 (Crítica)
**Estimativa:** 2-3 dias

---

## 1. Objetivo

Integrar o LoadPredictor centralizado no fluxo de enriquecimento de tickets do Orchestrator, permitindo que previsões de carga do sistema influenciem o scheduling de tarefas.

---

## 2. Problema Atual

**Análise:**
- `LoadPredictor` (neural_hive_ml) é criado e injetado em `IntelligentScheduler`
- Mas `_enrich_ticket_with_predictions()` NÃO usa `self.load_predictor`
- O LoadPredictor tem métodos úteis: `predict_load()` e `predict_bottlenecks()`

**Arquivo Crítico:**
- `/services/orchestrator-dynamic/src/scheduler/intelligent_scheduler.py:556-627`

---

## 3. Abordagem de Implementação

### 3.1 Modificar `_enrich_ticket_with_predictions`

```python
# intelligent_scheduler.py

async def _enrich_ticket_with_predictions(self, ticket: dict) -> dict:
    """Enriquece ticket com previsões de ML e anomalias"""
    predictions = {}
    
    # Predições de duração e recursos (existente)
    if self.scheduling_predictor:
        duration_pred = await self.scheduling_predictor.predict_duration(ticket)
        predictions["duration"] = duration_pred
        ...
    
    # Detecção de anomalias (existente)
    if self.anomaly_detector:
        anomaly_result = await self.anomaly_detector.detect_anomaly(ticket)
        predictions["anomaly"] = anomaly_result
        ...
    
    # NOVO: Previsão de carga do sistema
    if self.load_predictor:
        load_forecast = await self.load_predictor.predict_load(
            horizon_minutes=60,
            features=ticket
        )
        predictions["system_load"] = load_forecast.get("predicted_load_pct", 0.5)
        
        # NOVO: Detecção de bottlenecks
        bottlenecks = await self.load_predictor.predict_bottlenecks(
            horizon_minutes=60,
            current_load=ticket
        )
        predictions["bottlenecks"] = bottlenecks
        
        # Enriquecer ticket com métricas
        ticket["predicted_load_pct"] = predictions["system_load"]
        ticket["predicted_bottlenecks"] = bottlenecks
    
    ticket["predictions"] = predictions
    return ticket
```

### 3.2 Adicionar Métricas

```python
# Métricas Prometheus
load_predictor_usage = Counter(
    "orchestrator_load_predictor_usage_total",
    "Total de usos do LoadPredictor",
    ["success", "failure"]
)

load_forecast_value = Gauge(
    "orchestrator_load_forecast_value",
    "Valor de forecast de carga do sistema"
)
```

---

## 4. Tickets (Decomposição)

| Ticket | Descrição | Estimativa |
|--------|-----------|------------|
| INFRA-011-01 | Integrar predict_load() em enrich_ticket | 0.5 dia |
| INFRA-011-02 | Integrar predict_bottlenecks() em enrich_ticket | 0.5 dia |
| INFRA-011-03 | Adicionar métricas Prometheus | 0.5 dia |
| INFRA-011-04 | Testes de integração | 0.5 dia |

---

## 5. Critérios de Aceite

- [ ] `load_predictor.predict_load()` chamado em `_enrich_ticket_with_predictions()`
- [ ] `load_predictor.predict_bottlenecks()` chamado em `_enrich_ticket_with_predictions()`
- [ ] Ticket enriquecido com `predicted_load_pct`
- [ ] Ticket enriquecido com `predicted_bottlenecks`
- [ ] Métricas Prometheus registadas
- [ ] Testes de integração passando

---

## 6. Testes

```python
# tests/integration/test_load_predictor_integration.py

@pytest.mark.asyncio
async def test_enrich_ticket_with_load_predictor():
    """Testa que ticket é enriquecido com previsões de carga"""
    scheduler = IntelligentScheduler(
        load_predictor=mock_load_predictor,
        scheduling_predictor=mock_scheduling_predictor,
        anomaly_detector=mock_anomaly_detector
    )
    
    ticket = {"task_id": "test-123", "type": "query"}
    enriched = await scheduler._enrich_ticket_with_predictions(ticket)
    
    assert "predicted_load_pct" in enriched
    assert "predicted_bottlenecks" in enriched
    assert enriched["predictions"]["system_load"] == pytest.approx(0.7, abs=0.2)
```

---

## 7. Handoff para Implementação

**Branch:** `feat/INFRA-011-loadpredictor-integration`

**Comandos:**
```bash
git checkout -b feat/INFRA-011-loadpredictor-integration

# Modificar intelligent_scheduler.py
# ... adicionar chamadas a load_predictor

# Adicionar métricas
# ... modificar src/metrics/

# Testes
pytest tests/integration/test_load_predictor_integration.py

# Commit
git add .
git commit -m "feat(orchestrator): integrate loadpredictor in ticket enrichment"
```

---

**Spec criada para:** INFRA-011
**Data:** 2026-04-14
