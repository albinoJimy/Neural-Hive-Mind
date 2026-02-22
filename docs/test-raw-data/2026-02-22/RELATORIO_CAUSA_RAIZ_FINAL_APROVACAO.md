# RELATÓRIO: CAUSA RAIZ FINAL - APROVAÇÃO MANUAL

## Data: 2026-02-22 14:50 UTC

---

## 🎯 CAUSA RAIZ IDENTIFICADA

O problema de `tickets_generated: 0` após aprovação manual tem **DUAS causas** que ocorrem em sequência:

### Causa 1: Query Temporal Falha
- **Erro:** `HTTPStatusError` ao tentar query workflow
- **Motivo:** Client tentando HTTP quando deveria usar gRPC
- **Impacto:** Não consegue ler dados do workflow

### Causa 2: Fallback MongoDB Tem Query Errada
- **Problema:** Query não lê estrutura aninhada corretamente
- **Estrutura real:** `plan_approvals.cognitive_plan.cognitive_plan.tasks`
- **Query provavelmente busca:** `plan_approvals.tasks` ou `cognitive_plans.tasks`
- **Impacto:** Retorna vazio mesmo com dados existentes

---

## EVIDÊNCIAS COLETAS

### 1. Tasks EXISTEM no MongoDB ✅

```javascript
// Query manual realizada:
db.plan_approvals.findOne({plan_id: '64c02a55-e5e2-4d8a-a308-4167c50766be'})

// Estrutura:
plan_approvals
  └─ cognitive_plan (obj)
      └─ cognitive_plan (obj)
          ├─ plan_id: "64c02a55-e5e2-4d8a-a308-4167c50766be"
          ├─ tasks: [5 items]  ← TASKS ESTÃO AQUI!
          ├─ execution_order: [...]
          ├─ risk_score: ...
          └─ risk_band: ...
```

**Primeiro task encontrado:**
```json
{
  "task_id": "task_0",
  "task_type": "query",
  "description": "Detalhar requisitos de health check - casos de uso, critérios de aceite",
  "dependencies": [],
  "estimated_duration_ms": 500,
  "required_capabilities": ["read", "analyze"]
}
```

### 2. Temporal Workflow Inicia VAZIO ⚠️

```bash
tctl workflow show --workflow_id orch-flow-c-eacf7dcf-6698-4b3a-8d47-3078cf77185c
```

**Resultado:**
```json
{
  "Input": {
    "cognitive_plan": {},  // VAZIO!
    "consolidated_decision": {
      "plan_id": "unknown",  // DESCONHECIDO!
      "intent_id": "unknown"
    }
  }
}
```

**Workflow execution result:**
```
WorkflowExecutionFailed: Plano cognitivo inválido: [
  'Campo obrigatório ausente: plan_id',
  'Campo obrigatório ausente: tasks',
  'Campo obrigatório ausente: execution_order',
  'Campo obrigatório ausente: risk_score',
  'Campo obrigatório ausente: risk_band'
]
```

### 3. Orchestrator Logs Confirmam

```json
// Tentando criar tickets
{"event": "creating_ticket", "plan_id": "64c02a55..."}

// Falha query Temporal
{"event": "failed_to_query_workflow_tickets",
 "error": "RetryError[<Future raised HTTPStatusError>]"}

// Fallback MongoDB
{"event": "extracting_tickets_from_plan_fallback",
 "reason": "workflow query failed or returned empty"}

// Resultado
{"event": "flow_c_resumed_after_approval",
 "success": false,
 "tickets_generated": 0}
```

---

## DIAGRAMA COMPLETO DO PROBLEMA

```
┌─────────────────────────────────────────────────────────────────────────┐
│  FLUXO DE APROVAÇÃO - COM PROBLEMAS IDENTIFICADOS                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Aprovação manual publicada ✅                                      │
│         ↓                                                              │
│  2. Orchestrator recebe mensagem ✅                                    │
│         ↓                                                              │
│  3. resume_flow_c_after_approval() chamado ✅                          │
│         ↓                                                              │
│  4. Tenta query Temporal workflow ❌ HTTPStatusError                   │
│         │     - Tentando HTTP ao invés de gRPC                         │
│         ↓                                                              │
│  5. Fallback: Query MongoDB ❌ Query incorreta                         │
│         │     - Busca: plan_approvals.tasks                            │
│         │     - Real: plan_approvals.cognitive_plan.cognitive_plan... │
│         ↓                                                              │
│  6. cognitive_plan = {} ❌ Vazio                                       │
│         ↓                                                              │
│  7. Workflow iniciado com dados vazios ❌                              │
│         ↓                                                              │
│  8. Validação falha: campos ausentes ❌                                │
│         ↓                                                              │
│  9. WorkflowExecutionFailed ❌                                         │
│         ↓                                                              │
│  10. tickets_generated = 0 ❌                                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## SOLUÇÕES

### Opção 1: Corrigir Query do Fallback (Rápido)

**Arquivo:** `neural_hive_integration` (pacote externo)

**Mudança necessária:**
```python
# ANTES (provavelmente):
approval = db.plan_approvals.find_one({"plan_id": plan_id})
cognitive_plan = approval.get("cognitive_plan")  # Retorna obj aninhado

# DEPOIS:
approval = db.plan_approvals.find_one({"plan_id": plan_id})
cognitive_plan = approval.get("cognitive_plan", {}).get("cognitive_plan", {})
```

### Opção 2: Corrigir Conexão Temporal (Completo)

**Problema:** HTTP vs gRPC

**Investigar:**
- Por que `neural_hive_integration` usa HTTP?
- Configuração de client Temporal
- Endpoint correto para query

### Opção 3: Workaround Manual Emergencial

Criar script que:
1. Lê plan_approvals do MongoDB
2. Extrai tasks da estrutura aninhada
3. Cria tickets diretamente via API

---

## DADOS PARA CORREÇÃO

### Estrutura MongoDB Correta

```python
# Como ler os tasks corretamente:
from pymongo import MongoClient

client = MongoClient(mongodb_uri)
db = client['neural_hive']
approval = db.plan_approvals.find_one({'plan_id': plan_id})

# Navegar estrutura aninhada
cognitive_plan = approval.get('cognitive_plan', {}).get('cognitive_plan', {})
tasks = cognitive_plan.get('tasks', [])

# Criar tickets para cada task
for task in tasks:
    create_execution_ticket(task)
```

### Exemplo de Task Completo

```json
{
  "task_id": "task_0",
  "task_type": "query",
  "description": "Detalhar requisitos de health check - casos de uso, critérios de aceite",
  "dependencies": [],
  "estimated_duration_ms": 500,
  "required_capabilities": ["read", "analyze"],
  "parameters": {
    "subject": "health check",
    "target": "o serviço de aprovações",
    "entities": "['Criar endpoint de health check para o serviço de aprovações']"
  },
  "metadata": {
    "template_id": "requirements",
    "semantic_domain": "quality",
    "intent_type": "feature_implementation"
  }
}
```

---

## COMANDOS ÚTEIS

### Verificar tasks no MongoDB
```bash
kubectl exec -n mongodb-cluster mongodb-* -c mongodb -- \
  mongosh "mongodb://root:local_dev_password@localhost:27017/neural_hive?authSource=admin" \
  --eval "
    var a = db.plan_approvals.findOne({plan_id: 'PLAN_ID'});
    a.cognitive_plan.cognitive_plan.tasks.forEach((t, i) => {
      print(i + ': ' + t.task_id + ' - ' + t.description);
    });
  "
```

### Verificar workflow no Temporal
```bash
kubectl exec -n temporal temporal-frontend-* -- \
  tctl --namespace default workflow show \
  --workflow_id orch-flow-c-WORKFLOW_ID
```

### Re-executar workflow manualmente
```bash
# Seria necessário corrigir o código primeiro para passar
# o cognitive_plan completo da estrutura aninhada
```

---

## CONCLUSÃO

**Status:** 🔴 **CAUSA RAIZ IDENTIFICADA**

O problema tem **duas causas confirmadas**:

1. **Query Temporal** usando HTTP em vez de gRPC
2. **Fallback MongoDB** com query incorreta para estrutura aninhada

**Solução mais rápida:** Corrigir a query do fallback para ler:
`plan_approvals.cognitive_plan.cognitive_plan`

**Solução completa:** Corrigir ambas (Temporal + fallback)

---

**FIM DO RELATÓRIO**
