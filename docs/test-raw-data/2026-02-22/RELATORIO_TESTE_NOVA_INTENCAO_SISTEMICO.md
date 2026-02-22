# RELATÓRIO: TESTE COM NOVA INTENÇÃO - PROBLEMA SISTÊMICO

## Data: 2026-02-22 14:40 UTC

---

## RESUMO EXECUTIVO

**Status:** ❌ PROBLEMA SISTÊMICO CONFIRMADO

O teste com uma nova intenção confirmou que o problema de criação de tickets após aprovação **não é específico a um plano antigo**, mas um **problema sistêmico** que afeta todo o fluxo de aprovação.

---

## DADOS DO TESTE

### Nova Intenção
- **Intent ID:** `fdd2a86f-0e11-4b7a-a03e-dee565b3cbc0`
- **Correlation ID:** `6aee86e6-a4e6-484a-ba87-1f830a6d22ed`
- **Trace ID:** `c616022eff6d5233f21f15815877a162`
- **Texto:** "Criar endpoint de health check para o serviço de aprovações"
- **Confidence:** 0.2 (low)
- **Status:** `routed_to_validation`

### Plano Gerado
- **Plan ID:** `64c02a55-e5e2-4d8a-a308-4167c50766be`
- **Decision:** `review_required`
- **Status Approval:** `pending` → `approved` (manual)

---

## VERIFICAÇÕES REALIZADAS

### 1. Tasks no MongoDB ❌

```javascript
// consensus_decisions - SEM campo tasks
db.consensus_decisions.findOne({plan_id: '64c02a55...'})
// Result: {plan_id, final_decision, ...} SEM tasks

// cognitive_ledger - SEM campo plan
db.cognitive_ledger.findOne({plan_id: '64c02a55...'})
// Result: {...} SEM plan/tasks

// workflow_results - NÃO encontrado
db.workflow_results.findOne({workflow_id: '64c02a55...'})
// Result: null
```

**Conclusão:** **Os tasks NUNCA são persistidos no MongoDB.**

### 2. Aprovação Manual ✅

```python
approval_message = {
    'plan_id': '64c02a55-e5e2-4d8a-a308-4167c50766be',
    'decision': 'approved',
    'approved_by': 'claude-code-tester'
}
# Publicado em cognitive-plans-approval-responses ✅
```

### 3. Processamento Orchestrator ⚠️

**Logs:**
```json
// Tentando criar tickets
{"event": "creating_ticket", "plan_id": "64c02a55...", "task_type": "code_generation"}

// Falha na query Temporal
{"event": "failed_to_query_workflow_tickets",
 "error": "RetryError[<Future raised HTTPStatusError>]"}

// Fallback MongoDB
{"event": "extracting_tickets_from_plan_fallback",
 "reason": "workflow query failed or returned empty"}

// Resultado final
{"event": "flow_c_resumed_after_approval",
 "success": false,
 "tickets_generated": 0,
 "tickets_completed": 0}
```

### 4. Tickets no Kafka ❌

```bash
# Busca por tickets do plano 64c02a55...
# Result: VAZIO - nenhum ticket criado
```

---

## DIAGRAMA DO PROBLEMA

```
┌─────────────────────────────────────────────────────────────────────────┐
│  FLUXO COM PROBLEMA SISTÊMICO                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Nova intenção ✅                                                    │
│         ↓                                                              │
│  2. STE gera tasks ✅                                                   │
│         ↓                                                              │
│  3. Consensus analisa ✅                                                │
│         ↓                                                              │
│  4. Approval request criada ✅                                         │
│         ↓                                                              │
│  5. Tasks persistidos? ❌ NÃO - apenas em Temporal                     │
│         ↓                                                              │
│  6. Aprovação manual ✅                                                 │
│         ↓                                                              │
│  7. Orchestrator tenta query Temporal ❌ HTTPStatusError              │
│         ↓                                                              │
│  8. Fallback MongoDB ❌ Tasks não existem                             │
│         ↓                                                              │
│  9. tickets_generated = 0 ❌                                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## ANÁLISE DA CAUSA RAIZ

### Problema 1: Tasks Não Persistidos

**Local onde tasks DEVEM estar:** `cognitive_plans` ou `workflows`
**Realidade:** Estas coleções não existem ou estão vazias

**Local onde tasks EXISTEM:** Apenas no state do Temporal workflow

### Problema 2: Query Temporal Falha

**Erro:** `HTTPStatusError` ao fazer query do workflow

**Configuração:**
- `TEMPORAL_HOST=temporal-frontend.temporal.svc.cluster.local`
- `TEMPORAL_PORT=7233`
- `TEMPORAL_TLS_ENABLED=false`

**Teste:**
- TCP 7233: ✅ Acessível
- HTTP /api/workflows/v1: ❌ Timeout

**Conclusão:** O Orchestrator ou o pacote `neural_hive_integration` está tentando fazer
uma requisição HTTP para o Temporal, mas o endpoint não responde.

### Problema 3: Sem Fallback Funcional

Quando a query Temporal falha, o sistema tenta fallback (ler do MongoDB),
mas como os tasks nunca foram persistidos lá, o fallback também falha.

---

## SOLUÇÕES POSSÍVEIS

### Opção 1: Corrigir Conexão Temporal (Recomendado)

**Investigar:**
- Por que `neural_hive_integration` está usando HTTP em vez de gRPC?
- Existe configuração errada de endpoint?
- O Temporal precisa ter HTTP API habilitada?

**Ações:**
1. Verificar código-fonte de `neural_hive_integration`
2. Testar com `tctl` (CLI do Temporal) para confirmar que workflow existe
3. Configurar corretamente o client gRPC

### Opção 2: Persistir Tasks no MongoDB

**Modificar o código para:**
- Quando plano é criado, persistir tasks no MongoDB
- Criar coleção `cognitive_plans` ou usar `workflows`
- Atualizar o fallback para ler desta coleção

### Opção 3: Implementar Endpoint de Emergência

**Criar endpoint no Orchestrator:**
- `POST /admin/resume-approval/{plan_id}`
- Lê decisão do consenso
- Extrai tasks do Temporal via tctl
- Cria tickets manualmente

---

## COMANDOS ÚTEIS

### Verificar se workflow existe no Temporal

```bash
# Instalar tctl
kubectl exec -n temporal temporal-frontend-* -- tctl \
  --namespace default workflow show \
  --workflow_id orch-flow-c-64c02a55-e5e2-4d8a-a308-4167c50766be
```

### Verificar tasks no Temporal

```bash
kubectl exec -n temporal temporal-frontend-* -- tctl \
  --namespace default workflow query \
  --workflow_id orch-flow-c-64c02a55-e5e2-4d8a-a308-4167c50766be \
  --query_type getTasks
```

### Listar workflows recentes

```bash
kubectl exec -n temporal temporal-frontend-* -- tctl \
  --namespace default workflow list \
  --query_page_size 10
```

---

## CONCLUSÃO

O teste confirmou que o problema de `tickets_generated: 0` após aprovação é **sistêmico** e afeta todos os planos.

**A causa raiz é dupla:**
1. Tasks não são persistidos no MongoDB
2. Query Temporal via HTTP falha

**Para resolver, é necessário:**
- Corrigir a conexão com Temporal (usar gRPC corretamente)
- OU implementar persistência de tasks no MongoDB como fallback

---

**Status:** 🔴 **CRITICAL** - Fluxo de aprovação quebrado para todos os planos

**Prioridade:** **ALTA** - Impede que planos aprovados sejam executados

---

**FIM DO RELATÓRIO**
