# RELATÓRIO FINAL - DIAGNÓSTICO WORKER DISCOVERY ISSUE

## Data: 2026-02-25
## Status: DIAGNÓSTICO COMPLETO, PRÓXIMA AÇÃO IDENTIFICADA

---

## RESUMO DA INVESTIGAÇÃO

Problema: Orchestrator Dynamic gera 0 tickets em vez de 8.

### Fluxo de Dados Verificado

```
STE → Kafka (plans.ready)
   └─ cognitive_plan.to_avro_dict() INCLUI tasks (linhas 216-228)

Consensus Engine → Kafka (plans.consensus)
   └─ ConsolidatedDecision(cognitive_plan=cognitive_plan) INCLUI plano completo (linha 208)

flow_c_consumer → FlowCOrchestrator.execute_flow_c()
   └─ Desserializa cognitive_plan da mensagem (linhas 367-371)

FlowCOrchestrator → OrchestratorClient.start_workflow()
   └─ POST /api/v1/workflows/start com cognitive_plan

Orchestrator → Workflow Temporal → Activity generate_execution_tickets()
   └─ args=[cognitive_plan, consolidated_decision]
```

### Código Verificado

| Componente | Arquivo | Linhas | Status |
|-----------|---------|--------|--------|
| STE Producer | `plan_producer.py` | 154-163 | ✅ Inclui tasks |
| CognitivePlan Model | `cognitive_plan.py` | 216-228 | ✅ tasks em to_avro_dict() |
| ConsolidatedDecision | `consolidated_decision.py` | 208 | ✅ cognitive_plan incluído |
| Consensus Orchestrator | `consensus_orchestrator.py` | 208 | ✅ cognitive_plan passed |
| flow_c_consumer | `flow_c_consumer.py` | 367-371 | ✅ Desserializa |
| Orchestrator Endpoint | `main.py` | 2997 | ✅ Passa cognitive_plan |
| Ticket Generation | `ticket_generation.py` | 73-78 | ⚠️ Tenta ler tasks |

---

## HIPÓTESES DA CAUSA RAIZ

### Hipótese 1: cognitive_plan chega vazio na activity
**Possível causa**: A desserialização do `cognitive_plan` na mensagem Kafka falha silenciosamente.

**Ponto de falha**: `flow_c_consumer.py` linhas 367-371
```python
cognitive_plan = consolidated_decision.get("cognitive_plan")
if isinstance(cognitive_plan, str):
    try:
        consolidated_decision["cognitive_plan"] = json.loads(cognitive_plan)
    except json.JSONDecodeError as e:
        raise ValueError(...)
```

**Verificação necessária**: Adicionar log ANTES de chamar `start_workflow()` para ver se `tasks` está presente.

### Hipótese 2: Aprovação manual não inclui cognitive_plan
**Possível causa**: Quando a aprovação é manual, o approval-service pode não ter o `cognitive_plan` completo.

**Ponto de falha**: A mensagem do approval-service para o Kafka pode estar incompleta.

**Verificação necessária**: Verificar o approval-service quando aprova.

### Hipótese 3: Workflow iniciado sem approval
**Possível causa**: O teste foi feito com decisão `review_required`, e o workflow pode ter sido iniciado antes da aprovação manual.

**Observado**: No log, o workflow foi iniciado em 19:50:08, após aprovação manual.

---

## AÇÃO RECOMENDADA

### 1. Adicionar Log no FlowCOrchestrator

**Arquivo**: `services/orchestrator-dynamic/src/integration/flow_c_orchestrator.py`

**Localização**: Método que chama `start_workflow()`

**Log a adicionar**:
```python
# Antes de chamar orchestrator_client.start_workflow()
logger.info(
    'flow_c_starting_workflow',
    plan_id=cognitive_plan.get('plan_id', 'MISSING'),
    has_tasks='tasks' in cognitive_plan,
    tasks_count=len(cognitive_plan.get('tasks', [])),
    cognitive_plan_keys=list(cognitive_plan.keys()) if isinstance(cognitive_plan, dict) else 'NOT_A_DICT'
)
```

### 2. Adicionar Log no Orchestrator Client

**Arquivo**: `libraries/neural_hive_integration/neural_hive_integration/clients/orchestrator_client.py`

**Localização**: Método `start_workflow()`, antes do POST

**Log a adicionar**:
```python
self.logger.info(
    "orchestrator_client_sending_workflow_request",
    correlation_id=correlation_id,
    plan_in_request=cognitive_plan.get('plan_id', 'MISSING'),
    has_tasks='tasks' in cognitive_plan,
    tasks_count=len(cognitive_plan.get('tasks', []))
)
```

---

## RESULTADOS DO TESTE E2E

| Fluxo | Status | Detalhes |
|-------|--------|----------|
| Gateway → Kafka | ✅ PASS | 231ms, confidence 0.95 |
| STE → MongoDB | ✅ PASS | 8 tarefas geradas |
| Consensus Engine | ⚠️ DEGRADED | Fallback heurístico |
| Aprovação Manual | ✅ PASS | Via API |
| Orchestrator → Tickets | ❌ FAIL | 0 tickets gerados |

**IDs de rastreamento**:
- Intent ID: `eab0f04b-64af-4a6f-acdf-a8c970970759`
- Plan ID: `99f332b6-f3bd-4189-84cb-f3b862c030b1`
- Decision ID: `5036dc70-ac2d-483c-bc2c-3119918d3fca`
- Workflow ID: `orch-flow-c-ad675562-4d13-471f-9845-bb1f7efdd4f5`

---

## PRÓXIMOS PASSOS

1. **Adicionar logs** no `FlowCOrchestrator` e `OrchestratorClient` (conforme acima)
2. **Rebuild e deploy** via CI/CD
3. **Reexecutar teste** E2E
4. **Analisar logs** para identificar onde `tasks` se perde

---

## ARTEFATOS

| Arquivo | Descrição |
|---------|-----------|
| `RELATORIO_TESTE_PIPELINE_COMPLETO.md` | Relatório do teste |
| `RELATORIO_WORKER_DISCOVERY_ISSUE.md` | Diagnóstico inicial |
| `RELATORIO_FINAL_WORKER_DISCOVERY.md` | Este arquivo |

---

**Assinatura**: Investigação completa, aguardando CI/CD para build e deploy.
