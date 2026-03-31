# Tasks — Critical Risks Mitigation

> Epic: Critical Risks Mitigation
> Data: 2026-03-31
> Estimativa Total: 36 horas (~5 dias)

---

## Tasks

### Sprint 1: Riscos Críticos (Dia 1-2)

- [x] 1. **CR-01: Remover JWT Secret Hardcoded** ✅
    - [x] 1.1 Criar VaultClient para Gateway
    - [x] 1.2 Modificar settings.py para usar Vault
    - [x] 1.3 Remover JWT_SECRET hardcoded
    - [x] 1.4 Criar script vault-seed.sh
    - [x] 1.5 Escrever testes unitários para VaultClient
    - [x] 1.6 Verificar CI/CD não detecta secrets
    - [x] 1.7 Commit e PR

- [x] 2. **CR-02: Implementar Scout Consumer Completo** ✅
    - [x] 2.1 Criar modelo DigitalEvent
    - [x] 2.2 Implementar DigitalEventsConsumer
    - [x] 2.3 Integrar consumer no main.py
    - [x] 2.4 Escrever teste de integração
    - [x] 2.5 Verificar métricas de consumo
    - [x] 2.6 Commit e PR

### Sprint 2: Cobertura de Testes (Dia 3-4)

- [x] 3. **CR-03: Testes para drift_monitoring** ✅
    - [x] 3.1 Escrever testes para DriftMonitor
    - [x] 3.2 Testar detecção de MEAN_SHIFT
    - [x] 3.3 Testar detecção de VARIANCE_CHANGE
    - [x] 3.4 Verificar cobertura ≥70%
    - [x] 3.5 Commit e PR

- [x] 4. **CR-04: Testes para observability** ✅
    - [x] 4.1 Escrever testes para MetricsCollector
    - [x] 4.2 Escrever testes para Structlog
    - [x] 4.3 Escrever testes para Tracing
    - [x] 4.4 Verificar cobertura ≥70%
    - [x] 4.5 Commit e PR

- [x] 5. **CR-05: Testes para compliance** ✅
    - [x] 5.1 Escrever testes para PolicyValidator
    - [x] 5.2 Escrever testes para AuditTrail
    - [x] 5.3 Verificar cobertura ≥70%
    - [x] 5.4 Commit e PR

- [x] 6. **CR-06: Testes para ledger** ✅
    - [x] 6.1 Escrever testes para Ledger persistence
    - [x] 6.2 Escrever testes para Ledger queries
    - [x] 6.3 Verificar cobertura ≥70%
    - [x] 6.4 Commit e PR

### Sprint 3: E2E e CI/CD (Dia 5)

- [x] 7. **CR-07: Smoke Tests E2E** ✅
    - [x] 7.1 Criar estrutura de smoke tests
    - [x] 7.2 Criar conftest.py
    - [x] 7.3 Escrever test_smoke_gateway.py
    - [x] 7.4 Escrever test_smoke_ste.py
    - [x] 7.5 Escrever test_smoke_consensus.py
    - [x] 7.6 Criar script run_smoke_tests.sh
    - [x] 7.7 Verificar execução <10min
    - [x] 7.8 Commit e PR

- [x] 8. **CR-08: Configurar Threshold de Cobertura** ✅
    - [x] 8.1 Criar coverage_config.ini
    - [x] 8.2 Criar GitHub workflow
    - [x] 8.3 Criar script check_coverage.sh
    - [x] 8.4 Configurar threshold 70%
    - [x] 8.5 Testar pipeline localmente
    - [x] 8.6 Commit e PR

- [x] 9. **CR-09: Documentação e Handoff** ✅
    - [x] 9.1 Actualizar feature-map.md
    - [x] 9.2 Actualizar MEMORY.md
    - [x] 9.3 Criar relatório final
    - [x] 9.4 Commit e PR

---

## Ordem de Execução Recomendada

1. **CR-01** (Sem dependências, crítico)
2. **CR-02** (Sem dependências, alta prioridade)
3. **CR-03** (Sem dependências)
4. **CR-04** (Sem dependências)
5. **CR-07** (Sem dependências, valor imediato)
6. **CR-05** (Sem dependências)
7. **CR-06** (Sem dependências)
8. **CR-08** (Depende de testes escritos)
9. **CR-09** (Depende de todos anteriores)

---

## Branches

```
feat/CR-01-remover-credenciais-hardcoded
feat/CR-02-scout-consumer-completo
feat/CR-03-testes-drift-monitoring
feat/CR-04-testes-observability
feat/CR-05-testes-compliance
feat/CR-06-testes-ledger
feat/CR-07-smoke-tests-e2e
feat/CR-08-configurar-cobertura-ci
feat/CR-09-documentacao-final
```

---

## Conclusão

- [x] Todos os 9 tickets completados ✅
- [x] Todos os testes passando ✅
- [x] Cobertura ≥70% em módulos críticos ✅
- [x] Zero credenciais hardcoded ✅
- [x] Smoke tests <10min ✅
- [x] Scout Agents funcionais ✅
- [x] CI/CD configurado ✅
- [x] Documentação actualizada ✅
