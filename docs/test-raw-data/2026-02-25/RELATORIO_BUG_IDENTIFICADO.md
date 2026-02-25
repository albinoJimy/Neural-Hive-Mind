# BUG IDENTIFICADO - 0 Tickets Gerados

## Data: 2026-02-25

## Problema

Orchestrator Dynamic gera 0 execution tickets mesmo com plano contendo 8 tarefas.

## Causa Raiz

**Estrutura de dados aninhada incompatível entre Approval Service e Orchestrator**

### Fluxo de Dados

1. **STE** publica plano via `approval_producer.py`:
   ```python
   cognitive_plan.to_avro_dict()  # ← Plano completo com tasks
   ```

2. **approval_request_consumer.py** (linha 217) cria `ApprovalRequest`:
   ```python
   ApprovalRequest(
       plan_id=plan_data['plan_id'],
       cognitive_plan=plan_data  # ← Plano completo aninhado aqui!
   )
   ```

3. **MongoDB** (`plan_approvals` collection) estrutura:
   ```javascript
   {
     plan_id: '99f332b6...',
     risk_score: 0.5,
     cognitive_plan: {           // ← Nível 1
       plan_id: '...',
       tasks: [...]             // ← Tasks AQUI!
     }
   }
   ```

4. **approval_service.py** (linha 325) aprova e republica:
   ```python
   cognitive_plan=approval.cognitive_plan  # ← Estrutura aninhada!
   ```

5. **Orchestrator** (`ticket_generation.py` linha 81) tenta ler:
   ```python
   tasks = cognitive_plan.get('tasks', [])  # ← Retorna [] vazio!
   ```
   **Porque**: `tasks` está em `cognitive_plan['cognitive_plan']['tasks']`, não em `cognitive_plan['tasks']`!

## Locais do Bug

| Arquivo | Linha | Problema |
|---------|-------|----------|
| `approval_request_consumer.py` | 217 | `cognitive_plan=plan_data` cria aninhamento |
| `approval_service.py` | 325 | Passa `approval.cognitive_plan` sem "achatar" |
| `ticket_generation.py` | 81 | Assume `tasks` diretamente em `cognitive_plan` |

## Soluções Possíveis

### Opção 1: Corrigir no approval_service (RECOMENDADO)

**Arquivo**: `services/approval-service/src/services/approval_service.py`

**Localização**: Linha 319-326

**Correção**:
```python
# ANTES (linha 319-326):
response = ApprovalResponse(
    plan_id=plan_id,
    intent_id=approval.intent_id,
    decision='approved',
    approved_by=user_id,
    approved_at=decision.approved_at,
    cognitive_plan=approval.cognitive_plan  # ← Estrutura aninhada
)

# DEPOIS:
# Extrair o plano completo da estrutura aninhada
plan_data = approval.cognitive_plan
if 'cognitive_plan' in plan_data and isinstance(plan_data.get('cognitive_plan'), dict):
    # Se está aninhado, usar o plano interno
    plan_data = plan_data['cognitive_plan']

response = ApprovalResponse(
    plan_id=plan_id,
    intent_id=approval.intent_id,
    decision='approved',
    approved_by=user_id,
    approved_at=decision.approved_at,
    cognitive_plan=plan_data  # ← Plano "achatado"
)
```

### Opção 2: Corrigir no Orchestrator (ALTERNATIVA)

**Arquivo**: `services/orchestrator-dynamic/src/activities/ticket_generation.py`

**Localização**: Linha 73-81

**Correção**:
```python
# ANTES:
tasks = cognitive_plan.get('tasks', [])

# DEPOIS:
# Lidar com estrutura aninhada do approval service
plan_data = cognitive_plan
if 'cognitive_plan' in plan_data and isinstance(plan_data.get('cognitive_plan'), dict):
    # Se está aninhado, usar o plano interno
    plan_data = plan_data['cognitive_plan']

tasks = plan_data.get('tasks', [])
```

### Opção 3: Corrigir na raiz (MAIS ROBUSTO)

**Arquivo**: `services/approval-service/src/consumers/approval_request_consumer.py`

**Localização**: Linha 209-217

**Correção**:
```python
# Criar ApprovalRequest apenas com metadados essenciais
# e guardar o plano completo em nível raiz, não aninhado

# Metadados essenciais:
approval_request = ApprovalRequest(
    plan_id=plan_data.get('plan_id'),
    intent_id=plan_data.get('intent_id'),
    risk_score=plan_data.get('risk_score', 0.0),
    risk_band=risk_band,
    is_destructive=plan_data.get('is_destructive', False),
    destructive_tasks=plan_data.get('destructive_tasks', []),
    risk_matrix=plan_data.get('risk_matrix'),
    # CRUCIAL: cognitive_plan deve ser o plano completo "achatado"
    cognitive_plan=plan_data  # ← Já está correto, o problema é leitura posterior
)
```

Esta opção não resolve, porque o problema está em como o approval_service lê o cognitive_plan.

**MELHOR SOLUÇÃO**: Opção 1 + Opção 2 (defesa em profundidade)

## Teste de Verificação

```python
# Verificar estrutura antes de chamar workflow
if 'cognitive_plan' in cognitive_plan:
    logger.warning(
        'cognitive_plan_aninhado_detectado',
        plan_id=cognitive_plan.get('plan_id'),
        has_tasks_nivel1='tasks' in cognitive_plan,
        has_tasks_nivel2='cognitive_plan' in cognitive_plan and 'tasks' in cognitive_plan.get('cognitive_plan', {})
    )
```

## Status

- ✅ Causa raiz identificada
- ⏳ Correção pendente
- ⏳ Teste após correção pendente
