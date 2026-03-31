# Handoff: Orchestrator Saga Avançada e Priorização Dinâmica

**Data:** 2026-03-31
**Epic:** Orchestrator Saga & Priority
**Spec:** `.agent-os/specs/2026-03-31-orchestrator-saga-priority/spec.md`

---

## Overview

Este epic completa o Orchestrator Dynamic implementando dois recursos críticos:

1. **Saga Pattern Avançado** — Coordenador dedicado com estado persistente
2. **Priorização Dinâmica** — Filas por prioridade com re-priorização em tempo real

---

## Tickets Decompostos

### Épico: ORCH-001

#### Ticket ORCH-01: Saga Coordinator Core
**Prioridade:** CRÍTICA
**Estimativa:** 6 horas
**Dependências:** Nenhuma

**Descrição:** Implementar coordenador de saga com estado persistente e eventos

**Arquivos:**
- `services/orchestrator-dynamic/src/saga/saga_orchestrator.py` (NOVO)
- `services/orchestrator-dynamic/src/saga/saga_state.py` (NOVO)
- `services/orchestrator-dynamic/src/saga/saga_event_store.py` (NOVO)
- `services/orchestrator-dynamic/src/saga/saga_repository.py` (NOVO)
- `services/orchestrator-dynamic/src/saga/__init__.py` (NOVO)

**Acceptance Criteria:**
- [ ] SagaOrchestrator com estados PENDING/STARTED/IN_PROGRESS/COMPLETED/COMPENSATING/COMPENSATED/FAILED
- [ ] SagaState com campos: saga_id, workflow_id, status, steps, compensation_order
- [ ] SagaEventStore para eventos saga_created, saga_started, saga_step_completed, etc.
- [ ] SagaRepository com operações CRUD no MongoDB
- [ ] 5+ testes unitários passando

---

#### Ticket ORCH-02: Saga Retry Configuration
**Prioridade:** ALTA
**Estimativa:** 4 horas
**Dependências:** ORCH-01

**Descrição:** Implementar retries com backoff exponencial para compensação

**Arquivos:**
- `services/orchestrator-dynamic/src/saga/retry_config.py` (NOVO)
- `services/orchestrator-dynamic/src/saga/retry_policy.py` (NOVO)
- `services/orchestrator-dynamic/src/activities/compensation.py` (MODIFICAR)

**Acceptance Criteria:**
- [ ] SagaRetryConfig com max_attempts, initial_delay_ms, max_delay_ms, multiplier, jitter
- [ ] RetryPolicy com lógica de backoff exponencial
- [ ] Integração com compensate_ticket activity
- [ ] 3+ testes unitários passando

---

#### Ticket ORCH-03: Saga Events Integration
**Prioridade:** ALTA
**Estimativa:** 5 horas
**Dependências:** ORCH-01

**Descrição:** Publicar eventos de saga no Kafka para observabilidade

**Arquivos:**
- `services/orchestrator-dynamic/src/saga/saga_producer.py` (NOVO)
- `services/orchestrator-dynamic/src/saga/saga_metrics.py` (NOVO)
- `services/orchestrator-dynamic/src/workflows/orchestration_workflow.py` (MODIFICAR)

**Acceptance Criteria:**
- [ ] Publicação de eventos saga_* no Kafka
- [ ] Métricas de saga (count, duration, compensation_count)
- [ ] Integração no OrchestrationWorkflow
- [ ] 3+ testes de integração passando

---

#### Ticket ORCH-04: Saga Query API
**Prioridade:** MÉDIA
**Estimativa:** 3 horas
**Dependências:** ORCH-01

**Descrição:** Adicionar query no workflow para consultar estado de saga

**Arquivos:**
- `services/orchestrator-dynamic/src/workflows/orchestration_workflow.py` (MODIFICAR)

**Acceptance Criteria:**
- [ ] Query get_saga_state para consultar estado
- [ ] Retorna status, steps, compensation_order
- [ ] 2+ testes unitários passando

---

#### Ticket ORCH-05: Priority Queues Scheduler
**Prioridade:** CRÍTICA
**Estimativa:** 6 horas
**Dependências:** Nenhuma

**Descrição:** Implementar scheduler com filas por prioridade

**Arquivos:**
- `services/orchestrator-dynamic/src/scheduler/priority_queues.py` (NOVO)
- `services/orchestrator-dynamic/src/scheduler/queue_manager.py` (NOVO)
- `services/orchestrator-dynamic/src/scheduler/ticket_scheduler.py` (MODIFICAR ou CRIAR)

**Acceptance Criteria:**
- [ ] 4 filas: CRITICAL, HIGH, NORMAL, LOW
- [ ] Round-robin com peso (CRITICAL: 4, HIGH: 3, NORMAL: 2, LOW: 1)
- [ ] Enqueue por priority_score do PriorityCalculator
- [ ] 5+ testes unitários passando

---

#### Ticket ORCH-06: Dynamic Re-prioritization
**Prioridade:** ALTA
**Estimativa:** 5 horas
**Dependências:** ORCH-05

**Descrição:** Implementar re-priorização baseada em eventos

**Arquivos:**
- `services/orchestrator-dynamic/src/scheduler/reprioritizer.py` (NOVO)
- `services/orchestrator-dynamic/src/scheduler/sla_reprioritizer.py` (NOVO)
- `services/orchestrator-dynamic/src/consumers/sla_event_consumer.py` (NOVO)

**Acceptance Criteria:**
- [ ] Re-prioritização por SLA warning
- [ ] Re-prioritização por deadline approaching
- [ ] Re-prioritização por risk band change
- [ ] Consumer de eventos SLA
- [ ] 4+ testes de integração passando

---

#### Ticket ORCH-07: Preemption Manager
**Prioridade:** ALTA
**Estimativa:** 5 horas
**Dependências:** ORCH-05

**Descrição:** Implementar preempção de tickets de baixa prioridade

**Arquivos:**
- `services/orchestrator-dynamic/src/scheduler/preemption.py` (NOVO)
- `services/orchestrator-dynamic/src/scheduler/preemption_rules.py` (NOVO)
- `services/orchestrator-dynamic/src/scheduler/priority_queues.py` (MODIFICAR)

**Acceptance Criteria:**
- [ ] CRITICAL pode preempption LOW/NORMAL
- [ ] HIGH pode preempption LOW
- [ ] Preempção only se execution_time < 30%
- [ ] Preempção only se compensatable
- [ ] 4+ testes unitários passando

---

#### Ticket ORCH-08: Adaptive Priority
**Prioridade:** MÉDIA
**Estimativa:** 4 horas
**Dependências:** ORCH-05

**Descrição:** Implementar ajuste automático de prioridade baseado em histórico

**Arquivos:**
- `services/orchestrator-dynamic/src/scheduler/adaptive_priority.py` (NOVO)
- `services/orchestrator-dynamic/src/scheduler/priority_calculator.py` (MODIFICAR)

**Acceptance Criteria:**
- [ ] Ajuste baseado em tempo de execução médio
- [ ] Ajuste baseado em taxa de falha
- [ ] Ajuste baseado em recursos consumidos
- [ ] Histórico mantido por 7 dias
- [ ] 3+ testes unitários passando

---

#### Ticket ORCH-09: Integration Tests
**Prioridade:** ALTA
**Estimativa:** 5 horas
**Dependências:** ORCH-01, ORCH-02, ORCH-03, ORCH-05, ORCH-06, ORCH-07

**Descrição:** Testes de integração E2E para saga e priority

**Arquivos:**
- `services/orchestrator-dynamic/tests/integration/test_saga_integration.py` (NOVO)
- `services/orchestrator-dynamic/tests/integration/test_priority_integration.py` (NOVO)
- `services/orchestrator-dynamic/tests/integration/test_preemption_integration.py` (NOVO)

**Acceptance Criteria:**
- [ ] 5+ testes de saga integration
- [ ] 5+ testes de priority integration
- [ ] 3+ testes de preemption integration
- [ ] Todos os testes passando

---

#### Ticket ORCH-10: Documentation
**Prioridade:** BAIXA
**Estimativa:** 2 horas
**Dependências:** Todos anteriores

**Descrição:** Actualizar documentação com novos recursos

**Arquivos:**
- `docs/feature-map.md` (MODIFICAR)
- `services/orchestrator-dynamic/docs/SAGA_PATTERN.md` (NOVO)
- `services/orchestrator-dynamic/docs/PRIORITY_SCHEDULER.md` (NOVO)

**Acceptance Criteria:**
- [ ] feature-map.md actualizado (85% → 100%)
- [ ] Documentação de Saga Pattern
- [ ] Documentação de Priority Scheduler
- [ ] Diagramas de sequência

---

## Resumo do Epic

| Ticket | Prioridade | Estimativa | Dependências |
|--------|-----------|------------|--------------|
| ORCH-01 | CRÍTICA | 6h | — |
| ORCH-02 | ALTA | 4h | ORCH-01 |
| ORCH-03 | ALTA | 5h | ORCH-01 |
| ORCH-04 | MÉDIA | 3h | ORCH-01 |
| ORCH-05 | CRÍTICA | 6h | — |
| ORCH-06 | ALTA | 5h | ORCH-05 |
| ORCH-07 | ALTA | 5h | ORCH-05 |
| ORCH-08 | MÉDIA | 4h | ORCH-05 |
| ORCH-09 | ALTA | 5h | Múltiplas |
| ORCH-10 | BAIXA | 2h | Todas |
| **TOTAL** | — | **45h** | ~6 dias |

---

## Ordem de Execução Recomendada

1. **ORCH-01** (Foundation — sem dependências)
2. **ORCH-05** (Foundation — sem dependências, pode ser paralelo com ORCH-01)
3. **ORCH-02** (Depende de ORCH-01)
4. **ORCH-03** (Depende de ORCH-01)
5. **ORCH-06** (Depende de ORCH-05)
6. **ORCH-07** (Depende de ORCH-05)
8. **ORCH-04** (Depende de ORCH-01)
9. **ORCH-08** (Depende de ORCH-05)
7. **ORCH-09** (Depende de múltiplos)
10. **ORCH-10** (Documentação final)

---

## Branches

```
feat/ORCH-01-saga-coordinator-core
feat/ORCH-02-saga-retry-config
feat/ORCH-03-saga-events-integration
feat/ORCH-04-saga-query-api
feat/ORCH-05-priority-queues-scheduler
feat/ORCH-06-dynamic-reprioritization
feat/ORCH-07-preemption-manager
feat/ORCH-08-adaptive-priority
feat/ORCH-09-integration-tests
feat/ORCH-10-documentation
```

---

## Estrutura de Directórios

```
services/orchestrator-dynamic/
├── src/
│   ├── saga/ (NOVO)
│   │   ├── __init__.py
│   │   ├── saga_orchestrator.py
│   │   ├── saga_state.py
│   │   ├── saga_event_store.py
│   │   ├── saga_repository.py
│   │   ├── retry_config.py
│   │   ├── retry_policy.py
│   │   ├── saga_producer.py
│   │   └── saga_metrics.py
│   ├── scheduler/
│   │   ├── priority_queues.py (NOVO)
│   │   ├── queue_manager.py (NOVO)
│   │   ├── reprioritizer.py (NOVO)
│   │   ├── sla_reprioritizer.py (NOVO)
│   │   ├── preemption.py (NOVO)
│   │   ├── preemption_rules.py (NOVO)
│   │   ├── adaptive_priority.py (NOVO)
│   │   ├── priority_calculator.py (MODIFICAR)
│   │   └── affinity_tracker.py
│   ├── consumers/
│   │   └── sla_event_consumer.py (NOVO)
│   ├── workflows/
│   │   └── orchestration_workflow.py (MODIFICAR)
│   └── activities/
│       └── compensation.py (MODIFICAR)
├── tests/
│   ├── unit/
│   │   ├── saga/ (NOVO)
│   │   └── scheduler/ (NOVO)
│   └── integration/
│       ├── test_saga_integration.py (NOVO)
│       ├── test_priority_integration.py (NOVO)
│       └── test_preemption_integration.py (NOVO)
└── docs/
    ├── SAGA_PATTERN.md (NOVO)
    └── PRIORITY_SCHEDULER.md (NOVO)
```

---

## Instruções para Claude Code

### 1. Seguir TDD

Para cada ticket:
1. Escrever testes primeiro
2. Verificar que falham
3. Implementar código mínimo
4. Verificar que passam
5. Fazer commit

### 2. Commits

Formato de commit:
```
feat(scope): descrição curta

- mudança 1
- mudança 2

Refs: ORCH-XX
```

### 3. Branch Naming

```
feat/ORCH-XX-[breve-descricao]
```

---

## Checklist de Conclusão

Antes de considerar o epic completo:

- [ ] Todos os 10 tickets implementados
- [ ] Todos os testes passando (unitários + integração)
- [ ] Saga events publicados no Kafka
- [ ] Priority queues funcionando
- [ ] Preemption testada e validada
- [ ] Adaptive priority configurado
- [ ] Documentação actualizada
- [ ] feature-map.md com 100% de completude

---

**Fim do Handoff**
