# Contract Pin — Neural-Hive-Mind Fluxos Principais

> **Tipo:** Refactor (Auditoria Arquitectural)
> **Objetivo:** Identificar riscos sem modificar comportamentos existentes
> **Restrição:** Análise deve PRESERVAR todos os invariantes abaixo

---

## Frozen Public API

*Durante a auditoria, estas APIs NÃO podem ser consideradas como alvo de modificação:*

### Kafka Topics (R-T7, R-T8)
- `nhm.intentions` - entrada de intenções do Gateway
- `nhm.plans` - planos cognitivos do STE
- `nhm.decisions` - decisões consolidadas do Consensus
- `nhm.approval-requests` - solicitações de aprovação humana
- `nhm.execution-tickets` - tickets de execução distribuída

**Ordem estrita:** intentions → plans → decisions → approval-requests → execution-tickets

### gRPC Services (R-I6, R-I7)
- `consensus-engine.ConsensusOrchestrator` - orquestração de especialistas
- `approval-service.ApprovalService` - aprovação de decisões sensíveis
- `service-registry.Registry` - descoberta de serviços

### REST APIs (R-I4, R-I5)
- `gateway-intencoes:8000/api/v1/intentions` - entrada principal
- `approval-service:8004/api/v1/approvals` - interface humana

---

## Allowed Internal Churn

*A auditoria pode QUESTIONAR estes aspectos, mas NÃO propor mudanças sem análise custo/benefício:*

- **Mecanismos de persistência** (MongoDB indexes, Redis TTL)
- **Estratégias de retry** (circuit breakers, timeouts)
- **Algoritmos de consenso** (pesos, merge strategies)
- **Workflows Temporal** (compensation logic)
- **Feature flags** (toggle de especialistas)

*Nota: A análise pode identificar riscos nestes componentes, mas as mitigações são out-of-scope desta spec.*

---

## Invariants (MUST Preserve)

Estes invariantes arquitecturais **NÃO podem ser violados** por qualquer mitigação futura. A auditoria deve identificar riscos que **não quebrem** estas verdades fundamentais.

### INV-1: Independência entre Camadas (R-B12, R-I1)
**Regra:** Gateway nunca chama Workers diretamente
**Fluxo correto:** Gateway → STE → Consensus → Orchestrator → Workers
**Violação:** Gateway publicando diretamente em `nhm.execution-tickets`
**Motivo:** Perda de tradução semântica, validação de consenso, orquestração

### INV-2: Unidirecionalidade dos Fluxos (R-T2)
**Regra:** Intenção → Plano → Decisão → Execução (nunca reverso sem compensação)
**Fluxo correto:** Cada etapa produziu novo artefacto downstream
**Violação:** Worker modificando CognitivePlan aprovado
**Compensação permitida:** Novo plano via Orchestrator (não mutação)
**Motivo:** Rastreabilidade, imutabilidade de decisões aprovadas

### INV-3: Isolamento de Failures (R-B6, R-I9)
**Regra:** Falha em specialist não derruba Consensus Orchestrator
**Comportamento esperado:** Timeout → specialist marcado unhealthy → rest continua
**Violação:** Exceção não tratada propaga para Orchestrator
**Motivo:** Resiliência do sistema, disponibilidade

### INV-4: Ordem Estrita dos Tópicos Kafka (R-T7, R-T8)
**Regra:** intentions → plans → decisions (nunca out-of-order)
**Garantia:** Timestamp em cada mensagem + consumer groups ordenados
**Violação:** Decisão publicada antes do Plan correspondente
**Motivo:** Consistência temporal, reproducibilidade

### INV-5: Imutabilidade de Planos Aprovados (R-T13)
**Regra:** CognitivePlan aprovado não pode ser modificado
**Estado final:** `status=approved` é frozen
**Mudança permitida:** Criar novo plano via Orchestrator (reference_to_previous)
**Violação:** Update direto em plan_approvals após aprovação
**Motivo:** Auditoria, non-repudiation, rastreabilidade

### INV-6: Single Source of Truth para Estado (R-B11)
**Regra:** MongoDB é autoritativo, Redis é cache apenas
**Leitura:** Sempre consultar MongoDB antes de Redis
**Escrita:** Escrever em ambos, mas MongoDB é fonte de verdade
**Violação:** Decisões baseadas apenas em Redis sem fallback MongoDB
**Motivo:** Consistência, recuperação de desastres

### INV-7: Atomicidade de Compensação Saga (R-T14)
**Regra:** Rollback compensatório deve ser idempotente
**Comportamento:** Executar compensação N vezes = mesmo estado final
**Violação:** Compensação com efeitos colaterais cumulativos
**Motivo:** Garantia de eventual consistency, segurança

### INV-8: Non-Blocking do Consensus Orchestrator (R-T5)
**Regra:** Timeout em specialist NÃO bloqueia novos pedidos
**Implementação:** asyncio.wait_for() + worker pool independente
**Violação:** Espera síncrona por todos os specialists (even if one hangs)
**Motivo:** Disponibilidade, isolamento de failures

### INV-9: Exclusividade do Queen Agent (R-B10)
**Regra:** Apenas uma instância ativa do Queen Agent
**Implementação:** Leader election via Redis ou MongoDB
**Violação:** Múltiplas instâncias tomando decisões estratégicas simultaneamente
**Motivo:** Consistência de decisões globais, race conditions

### INV-10: Idempotência de Execution Tickets (R-T15)
**Regra:** Mesmo ticket reprocessado não causa efeitos colaterais
**Implementação:** Deduplication via ticket_id + state machine
**Violação:** Worker executa mesma ação duas vezes (ex: duplicate payment)
**Motivo:** Garantia de exactly-once semantics, segurança

---

## Data Types (Read-Only para Análise)

Estes tipos são relevantes para a análise mas **não serão modificados**:

### CognitivePlan (R-T3, R-T4)
```python
{
  "plan_id": str,
  "original_intent_text": str,  # R-T3.4
  "translated_goal": dict,
  "specialists_required": list[str],
  "priority": int,
  "status": "draft" | "pending_consensus" | "approved" | "rejected",
  "created_at": datetime
}
```

### ConsolidatedDecision (R-T9, R-T10)
```python
{
  "decision_id": str,
  "plan_id": str,
  "consensus_type": "unanimous" | "majority" | "hierarchical",
  "specialist_opinions": list,
  "final_decision": dict,
  "confidence_score": float,
  "requires_approval": bool
}
```

### ExecutionTicket (R-T15)
```python
{
  "ticket_id": str,
  "decision_id": str,
  "worker_type": str,
  "payload": dict,
  "status": "pending" | "running" | "completed" | "failed" | "compensating",
  "retry_count": int,
  "created_at": datetime
}
```

---

## Audit Scope

A auditoria deve analisar:

### In-Scope (Análise de Riscos)
1. **Fluxos principais** (Gateway → STE → Consensus → Orchestrator → Workers)
2. **Casos de edge** (timeouts, failures, concorrência)
3. **Bottlenecks** (Kafka lag, MongoDB locks, Redis saturation)
4. **Single points of failure** (Queen Agent, Service Registry)
5. **Race conditions** (aprovações simultâneas, tickets duplicados)
6. **Memory leaks** (accumulation de state, não limpeza de cache)
7. **Security gaps** (autenticação inter-service, autorização)
8. **Observability gaps** (missing traces, métricas incompletas)
9. **Performance degradation** (slow queries, N+1 problems)
10. **Data inconsistency** (Mongo vs Redis sync, Kafka ordering)

### Out-of-Scope (Implementação)
- Código de mitigação
- Refatoração de implementação
- Mudanças de API
- Deploy de fixes

---

## Traceability

Todos os invariantes acima derivam dos requisitos:

- **R-B6, R-B10, R-B11, R-B12:** Base architectural principles
- **R-I1, R-I4-I7:** Integration contracts
- **R-T2-T15:** Transaction flow requirements

**Total de sub-requirements cobertos:** 26/52 (50% foco em transaction flows)
**Fontes principais:** R-T (transactions) e R-B (base principles)

---

## Non-Goals

Esta auditoria **NÃO** deve:

- Sugerir mudanças no protocolo de comunicação (Kafka → gRPC, etc.)
- Propor alteração da ordem dos tópicos
- Recomendar fusão de serviços (ex: STE + Consensus)
- Questionar a existência de algum serviço core
- Redefinir o modelo de dados (MongoDB schemas)

*Se a auditoria identificar que um destes não-goals é necessário para mitigar risco crítico, deve ser documentado como "ambiguity" requerendo decisão arquitetural.*
