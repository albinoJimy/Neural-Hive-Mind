# Tasks — Orchestrator Saga Avançada e Priorização Dinâmica

> Epic: Orchestrator Saga & Priority
> Data: 2026-03-31
> Estimativa Total: 45 horas (~6 dias)

---

## Tasks

### Saga Pattern Avançado (Dia 1-3)

- [ ] 1. **ORCH-01: Saga Coordinator Core**
    - [ ] 1.1 Criar diretório src/saga/
    - [ ] 1.2 Implementar SagaState model
    - [ ] 1.3 Implementar SagaEventStore
    - [ ] 1.4 Implementar SagaRepository
    - [ ] 1.5 Implementar SagaOrchestrator
    - [ ] 1.6 Criar migration MongoDB para saga_states
    - [ ] 1.7 Escrever testes unitários (5+)
    - [ ] 1.8 Commit e PR

- [ ] 2. **ORCH-02: Saga Retry Configuration**
    - [ ] 2.1 Implementar SagaRetryConfig
    - [ ] 2.2 Implementar RetryPolicy com backoff exponencial
    - [ ] 2.3 Integrar com compensate_ticket activity
    - [ ] 2.4 Adicionar jitter para evitar thundering herd
    - [ ] 2.5 Escrever testes unitários (3+)
    - [ ] 2.6 Commit e PR

- [ ] 3. **ORCH-03: Saga Events Integration**
    - [ ] 3.1 Implementar SagaProducer para Kafka
    - [ ] 3.2 Implementar SagaMetrics
    - [ ] 3.3 Publicar eventos saga_created, saga_started, saga_step_completed
    - [ ] 3.4 Publicar eventos saga_compensating, saga_compensated
    - [ ] 3.5 Integrar no OrchestrationWorkflow
    - [ ] 3.6 Escrever testes de integração (3+)
    - [ ] 3.7 Commit e PR

- [ ] 4. **ORCH-04: Saga Query API**
    - [ ] 4.1 Adicionar query get_saga_state no workflow
    - [ ] 4.2 Retornar status, steps, compensation_order
    - [ ] 4.3 Escrever testes unitários (2+)
    - [ ] 4.4 Commit e PR

### Priority Queues (Dia 2-4)

- [ ] 5. **ORCH-05: Priority Queues Scheduler**
    - [ ] 5.1 Implementar PriorityQueues
    - [ ] 5.2 Implementar QueueManager
    - [ ] 5.3 Criar 4 filas (CRITICAL, HIGH, NORMAL, LOW)
    - [ ] 5.4 Implementar round-robin com peso
    - [ ] 5.5 Integrar com PriorityCalculator
    - [ ] 5.6 Escrever testes unitários (5+)
    - [ ] 5.7 Commit e PR

- [ ] 6. **ORCH-06: Dynamic Re-prioritization**
    - [ ] 6.1 Implementar RePrioritizer
    - [ ] 6.2 Implementar SLARePrioritizer
    - [ ] 6.3 Criar SLAEventConsumer
    - [ ] 6.4 Implementar lógica de re-priorização
    - [ ] 6.5 Escrever testes de integração (4+)
    - [ ] 6.6 Commit e PR

- [ ] 7. **ORCH-07: Preemption Manager**
    - [ ] 7.1 Implementar PreemptionManager
    - [ ] 7.2 Implementar PreemptionRules
    - [ ] 7.3 Implementar lógica de preempção
    - [ ] 7.4 Verificar compensatabilidade antes de preempção
    - [ ] 7.5 Escrever testes unitários (4+)
    - [ ] 7.6 Commit e PR

- [ ] 8. **ORCH-08: Adaptive Priority**
    - [ ] 8.1 Implementar AdaptivePriorityCalculator
    - [ ] 8.2 Implementar histórico de execução (7 dias)
    - [ ] 8.3 Implementar ajuste por tempo médio
    - [ ] 8.4 Implementar ajuste por taxa de falha
    - [ ] 8.5 Integrar com PriorityCalculator
    - [ ] 8.6 Escrever testes unitários (3+)
    - [ ] 8.7 Commit e PR

### Integração e Documentação (Dia 5-6)

- [ ] 9. **ORCH-09: Integration Tests**
    - [ ] 9.1 Criar test_saga_integration.py
    - [ ] 9.2 Criar test_priority_integration.py
    - [ ] 9.3 Criar test_preemption_integration.py
    - [ ] 9.4 Escrever 5+ testes de saga
    - [ ] 9.5 Escrever 5+ testes de priority
    - [ ] 9.6 Escrever 3+ testes de preemption
    - [ ] 9.7 Verificar todos os testes passando
    - [ ] 9.8 Commit e PR

- [ ] 10. **ORCH-10: Documentation**
    - [ ] 10.1 Actualizar feature-map.md (85% → 100%)
    - [ ] 10.2 Criar SAGA_PATTERN.md
    - [ ] 10.3 Criar PRIORITY_SCHEDULER.md
    - [ ] 10.4 Adicionar diagramas de sequência
    - [ ] 10.5 Actualizar MEMORY.md
    - [ ] 10.6 Commit e PR

---

## Ordem de Execução Recomendada

1. **ORCH-01** (Foundation — sem dependências)
2. **ORCH-05** (Foundation — sem dependências)
3. **ORCH-02** (Depende de ORCH-01)
4. **ORCH-03** (Depende de ORCH-01)
5. **ORCH-06** (Depende de ORCH-05)
6. **ORCH-07** (Depende de ORCH-05)
7. **ORCH-04** (Depende de ORCH-01)
8. **ORCH-08** (Depende de ORCH-05)
9. **ORCH-09** (Depende de múltiplos)
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

## Conclusão

- [ ] Todos os 10 tickets completados
- [ ] Todos os testes passando
- [ ] Saga events publicados no Kafka
- [ ] Priority queues funcionando
- [ ] Preemption testada
- [ ] Adaptive priority configurado
- [ ] Documentação actualizada
- [ ] Orchestrator Dynamic a 100%
