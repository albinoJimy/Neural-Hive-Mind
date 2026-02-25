# RELATÓRIO DE DIAGNÓSTICO - WORKER DISCOVERY ISSUE

## Data: 2026-02-25
## Teste: Pipeline Completo E2E
## Componente: Orchestrator Dynamic - Ticket Generation

---

## RESUMO

Durante o teste E2E do Pipeline Completo, o Orchestrator Dynamic iniciou o workflow com sucesso, validou o plano cognitivo, mas a activity `generate_execution_tickets` retornou **0 tickets** sem apresentar erros visíveis nos logs.

---

## SINTOMAS

### 1. Workflow Executado Com Sucesso
```
workflow_id: orch-flow-c-ad675562-4d13-471f-9845-bb1f7efdd4f5
plan_id: 99f332b6-f3bd-4189-84cb-f3b862c030b1
status: completed
```

### 2. Etapas do Workflow
| Etapa | Status | Observação |
|-------|--------|------------|
| C1: Validação do Plano | ✅ OK | Plano validado |
| C2: Geração de Tickets | ❌ FAIL | 0 tickets gerados |
| C3: Alocação de Recursos | ⚠️ SKIP | Nenhum ticket para alocar |
| C4: Publicação Kafka | ⚠️ SKIP | Nada publicado |
| C5: Consolidação | ⚠️ WARNING | VULN-003: plan_id não encontrado |

### 3. Log da Activity Ausente
**Esperado:** Log `"Gerando execution tickets para plano {plan_id}"` (linha 70)
**Observado:** Este log NÃO aparece nos logs do pod

Isso indica que a activity está falhando ANTES do primeiro log, ou não está sendo executada.

---

## DADOS COLETADOS

### Plano no MongoDB
```javascript
{
  plan_id: '99f332b6-f3bd-4189-84cb-f3b862c030b1',  // <-- NA RAIZ
  intent_id: 'eab0f04b-64af-4a6f-acdf-a8c970970759', // <-- NA RAIZ
  plan_data: {
    plan_id: '99f332b6-f3bd-4189-84cb-f3b862c030b1',
    tasks: [ ... 8 tarefas ... ],  // <-- 8 TAREFAS PRESENTES
    execution_order: [...],
    risk_band: 'medium',
    ...
  }
}
```

### Função get_cognitive_plan()
```python
async def get_cognitive_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
    document = await self.cognitive_ledger.find_one({'plan_id': plan_id})
    if not document:
        return None
    
    # Extrair plan_data e adicionar campos de identificação
    plan_data = document.get('plan_data', {})
    plan_data['plan_id'] = document.get('plan_id')  # <-- ADICIONA plan_id
    plan_data['intent_id'] = document.get('intent_id')  # <-- ADICIONA intent_id
    
    return plan_data
```

**Resultado Esperado:** `cognitive_plan` contém `tasks`, `plan_id`, `intent_id`, etc.

---

## HIPÓTESES

### Hipótese 1: cognitive_plan sem tasks
O `cognitive_plan` que chega na activity não tem a chave `tasks`.
- **Possível causa:** Alguém está chamando o endpoint `/api/v1/workflows/start` com um plano incompleto.
- **Verificação:** Necessário adicionar logs detalhados (já feito).

### Hipótese 2: Exceção silenciosa
A activity está lançando uma exceção antes do primeiro log:
- `KeyError` ao acessar `cognitive_plan["plan_id"]` na linha 70
- **Verificação:** A linha 70 acessa `cognitive_plan["plan_id"]` sem `.get()`, pode falhar.

### Hipótese 3: Activity não registrada
A activity não foi registrada no worker Temporal.
- **Verificado:** Activity está registrada em `temporal_worker.py` linha 422 e 423.

### Hipótese 4: Workflow iniciado com dados incorretos
O workflow foi iniciado via HTTP POST `/api/v1/workflows/start` com um `cognitive_plan` que não tem tasks.
- **Verificação:** Quem está chamando este endpoint?

---

## AÇÕES TOMADAS

### 1. Logs de Debug Adicionados
Arquivo: `services/orchestrator-dynamic/src/activities/ticket_generation.py`

**Antes:**
```python
logger.info(f'Gerando execution tickets para plano {cognitive_plan["plan_id"]}')
```

**Depois:**
```python
logger.info(
    'generate_execution_tickets_called',
    plan_id=cognitive_plan.get('plan_id', 'MISSING'),
    intent_id=cognitive_plan.get('intent_id', 'MISSING'),
    has_tasks='tasks' in cognitive_plan,
    tasks_count=len(cognitive_plan.get('tasks', [])),
    cognitive_plan_keys=list(cognitive_plan.keys()) if isinstance(cognitive_plan, dict) else 'NOT_A_DICT',
    consolidated_decision_keys=list(consolidated_decision.keys()) if isinstance(consolidated_decision, dict) else 'NOT_A_DICT'
)
```

### 2. Próximos Passos
1. **Rebuild** imagem do orchestrator-dynamic
2. **Redeploy** pod
3. **Reexecutar** teste E2E
4. **Analisar** novos logs para identificar causa raiz

---

## ARTEFATOS

| ID | Valor | Propósito |
|----|-------|-----------|
| Intent ID | `eab0f04b-64af-4a6f-acdf-a8c970970759` | Rastrear intenção original |
| Plan ID | `99f332b6-f3bd-4189-84cb-f3b862c030b1` | Rastrear plano cognitivo |
| Workflow ID | `orch-flow-c-ad675562-4d13-471f-9845-bb1f7efdd4f5` | Rastrear execução Temporal |

---

## STATUS

**Situação:** Aguardando rebuild e redeploy do orchestrator-dynamic para análise detalhada com novos logs.

**Bloqueador:** Sem logs detalhados, não é possível determinar a causa exata dos 0 tickets gerados.

**Recomendação:** Verificar quem está chamando `/api/v1/workflows/start` e qual `cognitive_plan` está sendo enviado.

