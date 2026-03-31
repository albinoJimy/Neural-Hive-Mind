# Spec Requirements Document

> Spec: Orchestrator Saga Avançada e Priorização Dinâmica
> Created: 2026-03-31
> Status: Planning

---

## Overview

Implementar dois recursos críticos no Orchestrator Dynamic para atingir 100% de completude: (1) Saga Pattern avançado com coordenador dedicado, estado persistente e eventos de saga, e (2) Priorização Dinâmica com filas por prioridade, re-priorização em tempo real e preempção de tickets.

---

## User Stories

### US-1: Saga Pattern Avançado

Como **engenheiro de confiabilidade**, quero **um coordenador de saga dedicado com estado persistente**, para garantir que operações distribuídas possam ser compensadas de forma confiável e rastreável.

**Workflow actual:**
- Compensação implementada apenas no workflow principal
- Estado de saga não é persistido separadamente
- Sem visibilidade do progresso de compensação
- Retries básicos sem backoff exponencial
- Sem eventos de saga para observabilidade

**Workflow desejado:**
- SagaCoordinator com estado persistente no MongoDB
- Eventos de saga (saga_started, step_completed, compensating, etc.)
- Retries com backoff exponencial configurável
- Compensação parcial quando apropriado
- Rollforward como alternativa ao rollback
- Query para consultar estado de saga

### US-2: Priorização Dinâmica

Como **engenheiro de orquestração**, quero **filas de prioridade e re-priorização dinâmica**, para garantir que tickets críticos sejam processados primeiro mesmo em condições de alta carga.

**Workflow actual:**
- PriorityCalculator existe mas não é integrado no scheduler
- Todos os tickets vão para a mesma fila
- Sem re-priorização baseada em eventos
- Sem preempção de tickets de baixa prioridade
- Prioridade estática desde criação até conclusão

**Workflow desejado:**
- Priority Queues (CRITICAL, HIGH, NORMAL, LOW)
- Re-priorização dinâmica baseada em eventos SLA
- Preempção de tickets de baixa prioridade
- Adaptive priority baseado em histórico
- API para ajuste manual de prioridade
- Métricas de priorização

---

## Spec Scope

1. **Saga Coordinator** — Coordenador dedicado com estado persistente, eventos e retries
2. **Priority Queues** — Filas por prioridade no scheduler
3. **Dynamic Re-prioritization** — Re-priorização baseada em eventos
4. **Preemption** — Preempção de tickets de baixa prioridade
5. **Adaptive Priority** — Ajuste automático baseado em histórico

## Out of Scope

- Refactor completo do Orchestrator Dynamic
- Mudanças de arquitectura dos Workers
- Novas activities além das necessárias para saga/priority

---

## Expected Deliverable

1. SagaCoordinator com estado persistente e eventos
2. PriorityQueuesScheduler com filas por prioridade
3. Re-prioritizationTrigger para ajuste dinâmico
4. PreemptionManager para preempção de tickets
5. AdaptivePriorityCalculator para ajuste automático
6. Testes de integração para ambos os features
7. Documentação de arquitectura

---

## Technical Specifications

### Saga Coordinator

**Componentes:**
- `SagaOrchestrator` — Coordenador principal de saga
- `SagaState` — Modelo de estado persistente
- `SagaEventStore` — Repositório de eventos
- `SagaRepository` — Persistência no MongoDB
- `SagaMetrics` — Métricas específicas de saga

**Estados de Saga:**
```
PENDING → STARTED → IN_PROGRESS → COMPLETED
                  ↘ COMPENSATING → COMPENSATED
                  ↘ FAILED
```

**Eventos de Saga:**
- `saga_created` — Saga criada
- `saga_started` — Execução iniciada
- `saga_step_completed` — Passo completado
- `saga_step_failed` — Passo falhou
- `saga_compensating` — Compensação iniciada
- `saga_compensated` — Compensação completada
- `saga_completed` — Saga completada com sucesso
- `saga_failed` — Saga falhou permanentemente

**Retry Configuration:**
```python
SagaRetryConfig(
    max_attempts=3,
    initial_delay_ms=1000,
    max_delay_ms=30000,
    multiplier=2.0,
    jitter=True
)
```

### Priority Queues

**Filas:**
- `CRITICAL` — Prioridade máxima (risk_band=critical, sla_urgency>80%)
- `HIGH` — Alta prioridade (risk_band=high, sla_urgency>50%)
- `NORMAL` — Prioridade normal (default)
- `LOW` — Baixa prioridade (risk_band=low, sla_urgency<50%)

**Scheduler Logic:**
```python
# Processamento round-robin com peso
for queue in [CRITICAL, HIGH, NORMAL, LOW]:
    if queue.has_tickets():
        if can_process(queue):
            ticket = queue.pop()
            process(ticket)
```

**Re-prioritization Events:**
- SLA warning → aumenta urgência
- Risk band change → reavalia score
- Deadline approaching → sobe para HIGH/CRITICAL
- Resource pressure → desce non-critical

### Preemption

**Regras de Preempção:**
1. Ticket CRITICAL pode preempption LOW/NORMAL
2. Ticket HIGH pode preempption LOW
3. Preempção only if execution_time < 30% total
4. Preempção only if compensatable

**Preemption Flow:**
1. Identificar ticket de baixa prioridade em execução
2. Verificar se é preemptível
3. Enviar signal de cancel
4. Aguardar compensação
5. Iniciar ticket de alta prioridade

### Adaptive Priority

**Factores de Ajuste:**
- Histórico de execução (sucesso/falha)
- Tempo médio de execução
- Recursos consumidos
- Feedback de especialistas

**Ajuste:**
```python
if avg_execution_time > expected * 1.5:
    priority_score *= 1.2  # Aumenta prioridade

if failure_rate > 0.2:
    priority_score *= 0.8  # Diminui prioridade (pode falhar)
```

---

## Dependencies

**Interno:**
- `services/orchestrator-dynamic/src/workflows/orchestration_workflow.py`
- `services/orchestrator-dynamic/src/activities/compensation.py`
- `services/orchestrator-dynamic/src/scheduler/priority_calculator.py`
- `services/orchestrator-dynamic/src/clients/mongodb_client.py`
- `services/orchestrator-dynamic/src/clients/kafka_producer.py`

**Externo:**
- MongoDB (para estado de saga e filas)
- Kafka (para eventos de saga e re-priorização)
- Temporal (para signals e queries)
