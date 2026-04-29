# Tickets P2 — Superfície de Falha do Orchestrator

> **Task:** Identificar e priorizar riscos em componentes não analisados na auditoria v1.0
> **Data:** 2026-04-28
> **Fonte:** Análise crítica via /hoyeon:discuss
> **Foco:** Orchestrator-dynamic e cascading failures

---

## Resumo Executivo

A auditoria v1.0 resolveu 10 gaps P0+P1 em serviços core (consensus-engine, observability, gdpr-erasure). No entanto, **37 serviços permaneceram não analisados**, sendo que **orchestrator-dynamic** é o ponto crítico identificado.

**Problema sistêmico:** O orchestrator-dynamic é o hub de orquestração mas:
1. Não tem circuit breaker com consensus-engine
2. Depende de queen-agent sem failover strategy
3. State pode divergir entre Temporal e MongoDB
4. Workers não têm recovery de progresso

---

## Tickets por Risco Crítico

### NHM-011: Implementar Circuit Breaker entre Orchestrator e Consensus

**Tipo:** Tech Debt / Resiliência
**Prioridade:** P0
**Score:** 180/180 (bloqueio crítico de fluxo)
**Esforço Estimado:** 3-5 dias
**Team:** Orchestrator Team
**Epic:** AUDITORIA-FLUXOS-P2-ORCHESTRATOR

#### Descrição
Orchestrator-dynamic depende de consensus-engine para decisões consolidadas, mas não há circuit breaker entre eles. Se consensus-engine falhar ou ficar lento, workflows penduram indefinidamente.

#### Impacto
- Workflows ficam em estado esperando decisão que nunca chega
- Temporal activities timeout sem recovery gracioso
- Cascading failure para todos os serviços dependentes

#### Critérios de Aceite
- [ ] Circuit breaker implementado em `consensus_client.py`
- [ ] Configuração: failure_threshold=5, recovery_timeout=30s
- [ ] Métricas de circuit state publicadas
- [ ] Fallback para decisão padrão ou rejeição graciosa
- [ ] Teste: consensus downtime não trava workflows

#### Dependencies
- Consensus Engine Team (definir SLA)
- Temporal Team (configurar timeouts)

#### Código Reference
```python
# File: orchestrator-dynamic/src/clients/consensus_client.py
from neural_hive_resilience.circuit_breaker import MonitoredCircuitBreaker

class ConsensusClient:
    def __init__(self):
        self.cb = MonitoredCircuitBreaker(
            service_name="orchestrator",
            circuit_name="consensus",
            failure_threshold=5,
            recovery_timeout=30,
        )

    async def get_consolidated_decision(self, plan_id: str):
        try:
            return await self.cb.call_async(self._grpc_call, plan_id)
        except CircuitBreakerError:
            # Fallback: rejeição graciosa
            return FallbackDecision(
                plan_id=plan_id,
                reason="consensus_unavailable",
                fallback_action="reject"
            )
```

#### Sub-tasks
- [ ] NHM-011-1: Implementar circuit breaker wrapper
- [ ] NHM-011-2: Definir fallback strategy
- [ ] NHM-011-3: Métricas e alertas
- [ ] NHM-011-4: Testes de integração
- [ ] NHM-011-5: Documentação

---

### NHM-012: Implementar DLQ no Approval-Service

**Tipo:** Tech Debt / Resiliência
**Prioridade:** P0
**Score:** 162/180
**Esforço Estimado:** 2-3 dias
**Team:** Approval Service Team
**Epic:** AUDITORIA-FLUXOS-P2-ORCHESTRATOR

#### Descrição
Approval-service consumer não tem DLQ implementada. Mensagens com schema inválido ou erros de processamento ficam presas no consumer indefinidamente, causando congestionamento.

#### Impacto
- Consumer bloqueia se encontrar mensagens inválidas
- Aprovações não são processadas
- Violação de flows que dependem de approval

#### Critérios de Aceite
- [ ] DLQ topic `nhm.approvals.dlq` criado
- [ ] Consumer envia mensagens inválidas para DLQ
- [ ] Métricas de DLQ depth publicadas
- [ ] Teste: mensagem inválida é roteada para DLQ

#### Dependencies
- Kafka Team (criar topic DLQ)

#### Sub-tasks
- [ ] NHM-012-1: Criar DLQ topic configuration
- [ ] NHM-012-2: Implementar DLQ handler no consumer
- [ ] NHM-012-3: Adicionar métricas
- [ ] NHM-012-4: Testes E2E

---

### NHM-013: Implementar Failover Strategy para Queen-Agent

**Tipo:** Tech Debt / Resiliência
**Prioridade:** P0
**Score:** 153/180
**Esforço Estimado:** 5-7 dias
**Team:** Queen Agent Team
**Epic:** AUDITORIA-FLUXOS-P2-ORCHESTRATOR

#### Descrição
Queen-agent não tem estratégia de failover visível. Se a queen ficar indisponível, tasks ficam órfãs sem redistribuição.

#### Impacto
- Tasks em execução são perdidas se queen falhar
- Single point of failure na coordenação
- Recover requer intervenção manual

#### Critérios de Aceite
- [ ] Leader election implementada (etcd/Redis)
- [ ] Re-eleição automática em caso de falha
- [ ] Tasks em execução são recuperadas por nova leader
- [ ] Teste: queen falha → reeleição → recovery

#### Dependencies
- Infra Team (etcd/Redis setup)

#### Sub-tasks
- [ ] NHM-013-1: Escolher estratégia de leader election
- [ ] NHM-013-2: Implementar heartbeat
- [ ] NHM-013-3: Implementar re-eleição
- [ ] NHM-013-4: Task recovery mechanism
- [ ] NHM-013-5: Testes de failover
- [ ] NHM-013-6: Documentação

---

### NHM-014: Implementar Fallback para Service-Registry

**Tipo:** Tech Debt / Resiliência
**Prioridade:** P1
**Score:** 144/180
**Esforço Estimado:** 2-3 dias
**Team:** Service Registry Team
**Epic:** AUDITORIA-FLUXOS-P2-ORCHESTRATOR

#### Descrição
Service-registry usa Redis como backend sem fallback. Se Redis falhar, o registry fica indisponível e workers não podem ser descobertos.

#### Impacto
- Workers não são encontrados
- Matching engine falha
- Tasks não são executadas

#### Critérios de Aceite
- [ ] Fallback para MongoDB quando Redis indisponível
- [ ] Cache warming após Redis recovery
- [ ] Teste: Redis down → fallback → recovery

#### Dependencies
- Data Team (validar schema MongoDB)

#### Sub-tasks
- [ ] NHM-014-1: Implementar fallback MongoDB
- [ ] NHM-014-2: Cache warming strategy
- [ ] NHM-014-3: Testes de integridade
- [ ] NHM-014-4: Métricas de fallback

---

### NHM-015: Implementar State Consistency Check (Temporal ↔ MongoDB)

**Tipo:** Tech Debt / Consistência
**Prioridade:** P0
**Score:** 135/180
**Esforço Estimado:** 5-7 dias
**Team:** Orchestrator Team
**Epic:** AUDITORIA-FLUXOS-P2-ORCHESTRATOR

#### Descrição
State pode divergir entre Temporal (workflow state) e MongoDB (execution tickets). Não há verificações de consistência entre as duas fontes de verdade.

#### Impacto
- Workflows podem ter estado inconsistente
- Recovery após falha pode usar dados stale
- Decisões baseadas em estado incorreto

#### Critérios de Aceite
- [ ] Job periódico de consistência (hourly)
- [ ] Alerta quando divergência > 1%
- [ ] Mechanismo de reconciliação automática
- [ ] Teste: divergência detectada e corrigida

#### Dependencies
- Temporal Team (API access)
- Data Team (MongoDB schema)

#### Sub-tasks
- [ ] NHM-015-1: Desenhar algoritmo de reconciliação
- [ ] NHM-015-2: Implementar consistency check job
- [ ] NHM-015-3: Implementar reconciliação
- [ ] NHM-015-4: Métricas e alertas
- [ ] NHM-015-5: Testes de divergência

---

### NHM-016: Implementar Worker Progress Recovery

**Tipo:** Tech Debt / Resiliência
**Prioridade:** P1
**Score:** 126/180
**Esforço Estimado:** 3-5 dias
**Team:** Worker Agents Team
**Epic:** AUDITORIA-FLUXOS-P2-ORCHESTRATOR

#### Descrição
Workers são single-threaded sem checkpointing. Se um worker falhar, o progresso da tarefa é perdido e a execução recomeça do zero.

#### Impacto
- Trabalho executado é perdido
- Timeout em tarefas longas
- Experiência de usuário degradada

#### Critérios de Aceite
- [ ] Checkpointing implementado para tarefas longas
- [ ] Recovery retoma de último checkpoint
- [ ] Teste: worker falha → recovery → continuação

#### Dependencies
- Orchestrator Team (coordenação)

#### Sub-tasks
- [ ] NHM-016-1: Desenhar protocolo de checkpoint
- [ ] NHM-016-2: Implementar checkpoint storage
- [ ] NHM-016-3: Implementar recovery logic
- [ ] NHM-016-4: Testes de recovery

---

### NHM-017: Implementar Rate Limiting em DLQ Producers

**Tipo:** Tech Debt / Estabilidade
**Prioridade:** P1
**Score:** 117/180
**Esforço Estimado:** 1-2 dias
**Team:** Observability Team
**Epic:** AUDITORIA-FLUXOS-P2-ORCHESTRATOR

#### Descrição
DLQ producers têm limite de 100 mensagens/minute. Bursts de erros podem saturar a DLQ e causar message loss sem controle.

#### Impacto
- Mensagens perdidas em bursts
- DLQ saturation não é monitorada
- Recovery becomes impossível

#### Critérios de Aceite
- [ ] Rate limiting implementado em DLQ producers
- [ ] Alerta quando DLQ approaching saturation
- [ ] Backpressure mechanism quando DLQ cheia
- [ ] Teste: burst de erros é controlado

#### Dependencies
- Kafka Team (topic capacity)

#### Sub-tasks
- [ ] NHM-017-1: Implementar rate limiting
- [ ] NHM-017-2: Implementar backpressure
- [ ] NHM-017-3: Métricas e alertas
- [ ] NHM-017-4: Testes de saturação

---

## Tabela Consolidada

| ID | Ticket | Prioridade | Score | Esforço | Team | Epic |
|----|--------|------------|-------|---------|------|------|
| NHM-011 | Circuit Breaker Orchestrator-Consensus | P0 | 180 | 3-5d | Orchestrator | P2-ORCH |
| NHM-012 | DLQ Approval-Service | P0 | 162 | 2-3d | Approval | P2-ORCH |
| NHM-013 | Queen-Agent Failover | P0 | 153 | 5-7d | Queen Agent | P2-ORCH |
| NHM-014 | Service-Registry Fallback | P1 | 144 | 2-3d | Registry | P2-ORCH |
| NHM-015 | State Consistency Check | P0 | 135 | 5-7d | Orchestrator | P2-ORCH |
| NHM-016 | Worker Progress Recovery | P1 | 126 | 3-5d | Workers | P2-ORCH |
| NHM-017 | DLQ Rate Limiting | P1 | 117 | 1-2d | Observability | P2-ORCH |

---

## Sprint Planning

### Sprint 1: Quick Wins (Semana 1-2)
- NHM-017: DLQ Rate Limiting (1-2d)
- NHM-012: DLQ Approval-Service (2-3d)

**Total:** 3-5 dias

### Sprint 2: Orchestrator Resiliência (Semana 3-5)
- NHM-011: Circuit Breaker (3-5d)
- NHM-014: Service-Registry Fallback (2-3d)

**Total:** 5-8 dias

### Sprint 3: State & Recovery (Semana 6-8)
- NHM-015: State Consistency Check (5-7d)
- NHM-016: Worker Progress Recovery (3-5d)

**Total:** 8-12 dias

### Sprint 4: Queen-Agent Failover (Semana 9-10)
- NHM-013: Queen-Agent Failover (5-7d)

**Total:** 5-7 dias

---

**Documento compilado por:** /hoyeon:discuss
**Data:** 2026-04-28
**Próximos passos:** Priorizar NHM-011 e NHM-012 (Sprint 1)
