# Análise de Consistência de Estado — Neural Hive Mind

> **Sub-requirements:** R-T3.1, R-T3.2, R-T3.3, R-B2.2, R-B6.2
> **Invariantes:** INV-6 (MongoDB = autoritativo, Redis = cache)

---

## 1. Duplicação de Estado (MongoDB vs Redis)

### INV-6 Verificação: Single Source of Truth

**Regra:** MongoDB é autoritativo, Redis é cache apenas.

#### Estado Atual

| Serviço | MongoDB (autoritativo) | Redis (cache) | Compliance INV-6 |
|---------|----------------------|---------------|------------------|
| gateway-intencoes | ✓ | ✓ (session state) | ✓ |
| consensus-engine | ✓ (decisões) | ✗ | ✗ |
| orchestrator-dynamic | ✓ (workflows) | ✓ (temporal state) | ⚠️ |
| approval-service | ✓ (approvals) | ✓ (pending queue) | ✓ |
| service-registry | ✓ | ✗ | ✗ |

**Problema:** `consensus-engine` e `service-registry` usam Redis como fonte primária para algumas operações.

#### Problemas Identificados

1. **Consensus Engine**: Cache hit ratio não monitorado
2. **Service Registry**: Health check state em Redis sem fallback MongoDB
3. **Orchestrator**: Temporal workflow state pode divergir de MongoDB

---

## 2. Race Conditions

### 2.1 Consensus Consolidation

**Problema:** Múltiplos especialistas podem emitir opiniões simultâneas.

**Código vulnerável:**
```python
# consensus-engine/src/services/consensus_orchestrator.py
async def consolidate_opinions(self, plan_id: str):
    opinions = await self._fetch_opinions(plan_id)
    # Race: opinions podem mudar durante processamento
    result = self._merge_opinions(opinions)
    await self._save_decision(result)
```

**Mitigação necessária:**
- Version stamp em CognitivePlan
- Optimistic locking no MongoDB

### 2.2 Concurrent Approvals

**Problema:** Mesmo approval pode ser processado por múltiplos workers.

**Risco:** Duplicação de execução.

**Estado atual:** Idempotency key existe mas não é validada consistentemente.

---

## 3. Kafka Message Ordering

### INV-4 Verificação: Ordem Estrita

**Regra:** intentions → plans → decisions (nunca out-of-order)

#### Análise

| Topic | Ordering Guarantee | Timestamp | Consumer Group |
|-------|-------------------|-----------|----------------|
| nhm.intentions | ✓ | `created_at` | gateway-group |
| nhm.plans | ✓ | `plan_ts` | ste-group |
| nhm.decisions | ✗ | ❌ missing | consensus-group |

**Problema:** `nhm.decisions` não tem timestamp explícito para ordering.

#### Out-of-Order Risk

**Cenário:** Decisão para Plan B chega antes de Decisão para Plan A (ambos da mesma intenção).

**Impacto:** Violação de INV-4.

---

## 4. Idempotency Gaps

### INV-10 Verificação: Idempotência de Execution Tickets

| Operação | Idempotente | Implementação |
|----------|-------------|---------------|
| Criar ticket | ✓ | `ticket_id` unique |
| Executar ticket | ✗ | Sem deduplication |
| Compensar ticket | ⚠️ | Parcial |
| Re-try ticket | ✗ | Pode duplicar |

**Problema:** Workers não verificam status antes de executar.

---

## 5. Recomendações de Mitigação

### Risco #1: State Divergence (Redis → MongoDB)

**Probabilidade:** ALTA
**Impacto:** ALTO
**Urgência:** Importante

**Mitigação:**
1. Implementar cache-aside pattern consistentemente
2. Adicionar cache invalidation events
3. Monitorar cache hit/miss ratio

### Risco #2: Race Condition em Consensus

**Probabilidade:** MÉDIA
**Impacto:** ALTO
**Urgência:** Crítico

**Mitigação:**
1. Adicionar version field a CognitivePlan
2. Implementar optimistic locking
3. Retry loop com backoff

### Risco #3: Kafka Out-of-Order

**Probabilidade:** BAIXA
**Impacto:** MÉDIO
**Urgência:** Moderado

**Mitigação:**
1. Adicionar timestamp a todas as mensagens
2. Implementar sequence number por intention_id
3. Consumer-side ordering buffer

---

## Matriz de Priorização

| # | Risco | Prob. | Imp. | Risco | Esforço | Prioridade |
|---|-------|-------|------|-------|---------|------------|
| 1 | State divergence Redis→Mongo | ALTA | ALTO | 9 | Médio (3-5 dias) | **P0** |
| 2 | Race condition consensus | MÉDIA | ALTO | 6 | Alto (5-7 dias) | **P1** |
| 3 | Kafka out-of-order | BAIXA | MÉDIO | 3 | Baixo (1-2 dias) | P2 |
| 4 | Non-idempotent execution | MÉDIA | ALTO | 6 | Médio (2-3 dias) | **P1** |

---

## Status de INV-6

**INV-6:** "MongoDB = autoritativo, Redis = cache apenas"

**Status:** ⚠️ **PARCIALMENTE VIOLADO**

- **Services compliant:** 3/5 (gateway, approval, orchestrator)
- **Services non-compliant:** 2/5 (consensus, registry)
- **Ação necessária:** Refactor consensus-engine e service-registry para cache-aside pattern
