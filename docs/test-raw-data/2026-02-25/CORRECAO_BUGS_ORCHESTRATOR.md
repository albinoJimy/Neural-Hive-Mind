# Relatório de Correção de Bugs - Orchestrator

## Data: 2026-02-25

---

## BUG 1: Serialização do ExecutionTicket - policy_decisions

### Status: ✅ CORRIGIDO

### Arquivo
`services/orchestrator-dynamic/src/activities/ticket_generation.py`

### Descrição
O campo `metadata['policy_decisions']` estava sendo atribuído diretamente como um `dict`, mas o schema Avro define `metadata` como `map<string, string>`, ou seja, todos os valores devem ser strings.

### Linhas Corrigidas
- **Linha 279**: `ticket['metadata']['policy_decisions'] = json.dumps(policy_result.policy_decisions)`
- **Linhas 377-383**: Bloco de merge de `policy_decisions` serializado como JSON

### Mudanças
1. Adicionado `import json` no topo do arquivo
2. Serialização de `policy_decisions` como string JSON antes de atribuir ao `metadata`

### Código Antes
```python
ticket['metadata']['policy_decisions'] = policy_result.policy_decisions  # dict
```

### Código Depois
```python
ticket['metadata']['policy_decisions'] = json.dumps(policy_result.policy_decisions)  # string JSON
```

---

## BUG 2: Falha na Criação de Tickets via HTTP 422

### Status: ✅ CORRIGIDO

### Arquivo
`libraries/neural_hive_integration/neural_hive_integration/orchestration/flow_c_orchestrator.py`

### Descrição
O método `_extract_tickets_from_plan()` (fallback usado quando workflow query falha) estava criando tickets com campos obrigatórios faltando, causando HTTP 422 Unprocessable Entity.

### Linhas Corrigidas
- **Linha 10**: Adicionado `import uuid`
- **Linhas 805-871**: Método `_extract_tickets_from_plan()` reescrito

### Campos Obrigatórios Adicionados
| Campo | Valor Default |
|-------|---------------|
| `ticket_id` | `str(uuid4())` |
| `intent_id` | `cognitive_plan.get("intent_id", "")` |
| `decision_id` | `context.decision_id ou "approval-{plan_id[:8]}"` |
| `correlation_id` | `cognitive_plan.get("correlation_id", "")` |
| `task_id` | `task.get("task_id", task.get("id", ...))` |
| `description` | `task.get("description", "")` |
| `status` | `"PENDING"` |
| `sla` | `{"deadline", "timeout_ms", "max_retries"}` |
| `qos` | `{"delivery_mode", "consistency", "durability"}` |
| `security_level` | `"INTERNAL"` |
| `created_at` | `int(datetime.utcnow().timestamp() * 1000)` |

### Mapeamentos Adicionados
- **task_type**: Mapeamento de tipos legados para TaskType do Avro
  - `query` → `QUERY`
  - `transform` → `TRANSFORM`
  - `validate` → `VALIDATE`
  - `code_generation` → `EXECUTE`

- **priority**: Mapeamento de prioridade
  - `high` → `HIGH`
  - `low` → `LOW`
  - `medium` → `NORMAL`

### Tratamento de Erro
Adicionado bloco `try/except` ao redor de `create_ticket()` para evitar que uma falha em um ticket interrompa a criação dos demais.

### Código Antes (Resumido)
```python
ticket_data = {
    "plan_id": context.plan_id,
    "task_type": task.get("type", "code_generation"),
    "required_capabilities": ...,
    "payload": {...},
    "sla_deadline": context.sla_deadline.isoformat(),
    "priority": context.priority,
}
# Faltavam 12+ campos obrigatórios!
```

### Código Depois (Resumido)
```python
ticket_data = {
    # Todos os campos obrigatórios do schema Avro
    "ticket_id": str(uuid4()),
    "plan_id": context.plan_id,
    "intent_id": intent_id,
    "decision_id": context.decision_id or f"approval-{context.plan_id[:8]}",
    "correlation_id": correlation_id,
    "task_id": task.get("task_id", ...),
    "task_type": normalized_task_type,
    "description": task.get("description", ""),
    "dependencies": task.get("dependencies", []),
    "status": "PENDING",
    "priority": normalized_priority,
    "risk_band": risk_band,
    "sla": {"deadline": sla_deadline, "timeout_ms": ..., "max_retries": 3},
    "qos": {"delivery_mode": "AT_LEAST_ONCE", "consistency": "EVENTUAL", "durability": "PERSISTENT"},
    "parameters": task.get("parameters", {}),
    "required_capabilities": ...,
    "security_level": "INTERNAL",
    "created_at": current_timestamp,
    # ... demais campos
}
```

---

## Impacto das Correções

### Antes
```
event: flow_c_resumed_after_approval
plan_id: 252e0a0b-7e30-4211-bc9b-e555adfb9bfe
success: false
tickets_generated: 0  ← Nenhum ticket criado!
tickets_completed: 0
duration_ms: 4354
```

### Depois (Esperado)
```
event: flow_c_resumed_after_approval
plan_id: xxx-xxx-xxx
success: true
tickets_generated: 8  ← Tickets criados com sucesso!
tickets_completed: 0
duration_ms: ~5000
```

---

## Testes Necessários

1. **Teste E2E com approval manual** - Validar que tickets são criados após aprovação
2. **Teste de fallback** - Validar `_extract_tickets_from_plan()` quando workflow query falha
3. **Teste de serialização** - Validar que `metadata['policy_decisions']` é string JSON

---

## Commits Sugeridos

```bash
git add libraries/neural_hive_integration/neural_hive_integration/orchestration/flow_c_orchestrator.py
git add services/orchestrator-dynamic/src/activities/ticket_generation.py
git commit -m "fix(orchestrator): corrige criação de tickets no fallback flow_c

- Adiciona todos os campos obrigatórios do schema Avro em _extract_tickets_from_plan
- Serializa policy_decisions como string JSON para compatibilidade com map<string, string>
- Adiciona tratamento de erro para evitar falha em cascata na criação de tickets
- Mapeia task_type e priority para valores válidos do schema Avro

Refs: docs/test-raw-data/2026-02-25/RELATORIO_TESTE_PIPELINE_COMPLETO.md"
```

---

## Verificação

```bash
# Verificar sintaxe
python -m py_compile libraries/neural_hive_integration/neural_hive_integration/orchestration/flow_c_orchestrator.py
python -m py_compile services/orchestrator-dynamic/src/activities/ticket_generation.py

# Rebuild da imagem (se necessário)
cd services/orchestrator-dynamic
docker build -t orchestrator-dynamic:fix .

# Redeploy no Kubernetes
kubectl set image deployment/orchestrator-dynamic orchestrator-dynamic=orchestrator-dynamic:fix -n neural-hive
```
