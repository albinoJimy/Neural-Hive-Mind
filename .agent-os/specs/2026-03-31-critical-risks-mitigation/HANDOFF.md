# 🎯 Handoff: Critical Risks Mitigation — Decomposição em Tickets

**Data:** 2026-03-31
**Epic:** Critical Risks Mitigation
**Spec:** `.agent-os/specs/2026-03-31-critical-risks-mitigation/spec.md`
**Plano:** `docs/superpowers/plans/2026-03-31-critical-risks-mitigation.md`

---

## 📋 Overview

Este epic visa mitigar os **4 riscos críticos** identificados na análise consolidada do Neural-Hive-Mind:

1. **Credenciais Hardcoded** — JWT secrets em código
2. **Baixa Cobertura de Testes** — 10-15% global, 0-5% em módulos críticos
3. **Testes E2E Lentos** — Desabilitados (>180min)
4. **Scout Consumer Stub** — Não consome eventos reais

---

## 🎫 Tickets Decompostos

### Épico: CRITICAL-RISKS

#### Ticket CR-01: Remover JWT Secret Hardcoded
**Prioridade:** CRÍTICA
**Estimativa:** 4 horas
**Dependências:** Nenhuma

**Descrição:** Migrar JWT secrets do Gateway para HashiCorp Vault

**Arquivos:**
- `services/gateway-intencoes/src/clients/vault_client.py` (NOVO)
- `services/gateway-intencoes/src/config/settings.py` (MODIFICAR)
- `services/gateway-intencoes/src/api/auth.py` (MODIFICAR)
- `scripts/vault-seed.sh` (NOVO)
- `services/gateway-intencoes/tests/unit/test_auth_vault.py` (NOVO)

**Acceptance Criteria:**
- [ ] Zero JWT secrets hardcoded no código
- [ ] VaultClient implementado com fallback para env var
- [ ] 3 testes unitários passando
- [ ] Script de setup Vault funcional
- [ ] CI/CD não detecta secrets no código

---

#### Ticket CR-02: Implementar Scout Consumer Completo
**Prioridade:** ALTA
**Estimativa:** 6 horas
**Dependências:** Nenhuma

**Descrição:** Implementar Kafka Consumer completo para eventos digitais dos Scout Agents

**Arquivos:**
- `services/scout-agents/src/consumers/digital_events_consumer.py` (NOVO)
- `services/scout-agents/src/models/digital_event.py` (NOVO)
- `services/scout-agents/src/main.py` (MODIFICAR)
- `services/scout-agents/tests/integration/test_digital_events_consumer.py` (NOVO)

**Acceptance Criteria:**
- [ ] DigitalEventsConsumer implementado
- [ ] Consome do tópico `digital.events`
- [ ] Deserialização Avro/JSON
- [ ] Integração com ExplorationEngine
- [ ] 1 teste de integração passando
- [ ] Métricas de consumo

---

#### Ticket CR-03: Testes para drift_monitoring
**Prioridade:** ALTA
**Estimativa:** 4 horas
**Dependências:** Nenhuma

**Descrição:** Escrever testes unitários para módulo drift_monitoring (cobertura actual 0%)

**Arquivos:**
- `libraries/python/neural_hive_ml/tests/unit/test_drift_monitoring.py` (NOVO)

**Acceptance Criteria:**
- [ ] 5+ testes unitários
- [ ] Cobertura ≥70% para drift_monitoring
- [ ] Testes para: MEAN_SHIFT, VARIANCE_CHANGE, serialização

---

#### Ticket CR-04: Testes para observability
**Prioridade:** ALTA
**Estimativa:** 4 horas
**Dependências:** Nenhuma

**Descrição:** Escrever testes unitários para módulo observability (cobertura actual 0%)

**Arquivos:**
- `libraries/python/neural_hive_observability/tests/unit/test_metrics.py` (NOVO)
- `libraries/python/neural_hive_observability/tests/unit/test_logging.py` (NOVO)
- `libraries/python/neural_hive_observability/tests/unit/test_tracing.py` (NOVO)

**Acceptance Criteria:**
- [ ] 10+ testes unitários
- [ ] Cobertura ≥70% para observability
- [ ] Testes para: MetricsCollector, Structlog, Tracing

---

#### Ticket CR-05: Testes para compliance
**Prioridade:** MÉDIA
**Estimativa:** 4 horas
**Dependências:** Nenhuma

**Descrição:** Escrever testes unitários para módulo compliance (cobertura actual 0%)

**Arquivos:**
- `libraries/python/neural_hive_compliance/tests/unit/test_policy_validator.py` (NOVO)
- `libraries/python/neural_hive_compliance/tests/unit/test_audit_trail.py` (NOVO)

**Acceptance Criteria:**
- [ ] 8+ testes unitários
- [ ] Cobertura ≥70% para compliance

---

#### Ticket CR-06: Testes para ledger
**Prioridade:** MÉDIA
**Estimativa:** 4 horas
**Dependências:** Nenhuma

**Descrição:** Escrever testes unitários para módulo ledger (cobertura actual ~5%)

**Arquivos:**
- `services/consensus-engine/tests/unit/test_ledger.py` (NOVO)

**Acceptance Criteria:**
- [ ] 6+ testes unitários
- [ ] Cobertura ≥70% para ledger
- [ ] Testes para: persistência, queries, validações

---

#### Ticket CR-07: Smoke Tests E2E
**Prioridade:** ALTA
**Estimativa:** 6 horas
**Dependências:** Nenhuma

**Descrição:** Criar smoke tests E2E para validação rápida (<10min)

**Arquivos:**
- `tests/e2e/smoke/conftest.py` (NOVO)
- `tests/e2e/smoke/test_smoke_gateway.py` (NOVO)
- `tests/e2e/smoke/test_smoke_ste.py` (NOVO)
- `tests/e2e/smoke/test_smoke_consensus.py` (NOVO)
- `tests/e2e/smoke/run_smoke_tests.sh` (NOVO)

**Acceptance Criteria:**
- [ ] 6+ smoke tests
- [ ] Execução <10min
- [ ] Testes para: Gateway, STE, Consensus, Specialists
- [ ] Script executável
- [ ] Integração no CI/CD

---

#### Ticket CR-08: Configurar Threshold de Cobertura
**Prioridade:** ALTA
**Estimativa:** 2 horas
**Dependências:** CR-03, CR-04, CR-05, CR-06

**Descrição:** Configurar threshold de 70% cobertura no CI/CD

**Arquivos:**
- `tests/coverage/coverage_config.ini` (NOVO)
- `.github/workflows/test-coverage.yml` (NOVO)
- `scripts/check_coverage.sh` (NOVO)

**Acceptance Criteria:**
- [ ] Config de cobertura criada
- [ ] GitHub workflow criado
- [ ] Pipeline bloqueia sem 70% cobertura
- [ ] Script local para verificar cobertura

---

#### Ticket CR-09: Documentação e Handoff
**Prioridade:** BAIXA
**Estimativa:** 2 horas
**Dependências:** Todos os anteriores

**Descrição:** Actualizar documentação com mudanças implementadas

**Arquivos:**
- `docs/feature-map.md` (MODIFICAR)
- `MEMORY.md` (MODIFICAR)

**Acceptance Criteria:**
- [ ] feature-map.md actualizado
- [ ] MEMORY.md actualizado
- [ ] Relatório final criado

---

## 📊 Resumo do Epic

| Ticket | Prioridade | Estimativa | Dependências |
|--------|-----------|------------|--------------|
| CR-01 | CRÍTICA | 4h | — |
| CR-02 | ALTA | 6h | — |
| CR-03 | ALTA | 4h | — |
| CR-04 | ALTA | 4h | — |
| CR-05 | MÉDIA | 4h | — |
| CR-06 | MÉDIA | 4h | — |
| CR-07 | ALTA | 6h | — |
| CR-08 | ALTA | 2h | CR-03,04,05,06 |
| CR-09 | BAIXA | 2h | Todos |
| **TOTAL** | — | **36h** | ~5 dias |

---

## 🚀 Instruções para Claude Code

### 1. Criar branches para cada ticket

```bash
# Exemplo para CR-01
git checkout -b feat/CR-01-remover-credenciais-hardcoded
```

### 2. Seguir o plano detalhado

O plano completo está em:
```
docs/superpowers/plans/2026-03-31-critical-risks-mitigation.md
```

### 3. Usar TDD

Para cada ticket:
1. Escrever testes primeiro
2. Verificar que falham
3. Implementar código mínimo
4. Verificar que passam
5. Fazer commit

### 4. Commits

Formato de commit:
```
feat(scope): descrição curta

- mudança 1
- mudança 2

Refs: CR-XX
```

### 5. Branch Naming

```
feat/CR-XX-[breve-descricao]
```

### 6. Após cada ticket

1. Fazer push da branch
2. Criar Pull Request
3. Aguardar review
4. Mergear após aprovação

---

## 📁 Estrutura de Directórios

```
Neural-Hive-Mind/
├── .agent-os/
│   └── specs/
│       └── 2026-03-31-critical-risks-mitigation/
│           ├── spec.md
│           └── spec-lite.md
├── docs/
│   └── superpowers/
│       └── plans/
│           └── 2026-03-31-critical-risks-mitigation.md
├── services/
│   ├── gateway-intencoes/
│   │   └── src/
│   │       ├── clients/
│   │       │   └── vault_client.py (NOVO)
│   │       ├── config/
│   │       │   └── settings.py (MODIFICAR)
│   │       ├── api/
│   │       │   └── auth.py (MODIFICAR)
│   │       └── tests/
│   │           └── unit/
│   │               └── test_auth_vault.py (NOVO)
│   └── scout-agents/
│       └── src/
│           ├── consumers/
│           │   └── digital_events_consumer.py (NOVO)
│           ├── models/
│           │   └── digital_event.py (NOVO)
│           ├── main.py (MODIFICAR)
│           └── tests/
│               └── integration/
│                   └── test_digital_events_consumer.py (NOVO)
├── libraries/
│   └── python/
│       ├── neural_hive_ml/
│       │   └── tests/
│       │       └── unit/
│       │           └── test_drift_monitoring.py (NOVO)
│       ├── neural_hive_observability/
│       │   └── tests/
│       │       └── unit/ (NOVOS)
│       └── neural_hive_compliance/
│           └── tests/
│               └── unit/ (NOVOS)
├── tests/
│   ├── e2e/
│   │   ├── smoke/ (NOVO)
│   │   │   ├── conftest.py
│   │   │   ├── test_smoke_*.py
│   │   │   └── run_smoke_tests.sh
│   │   └── full/ (NOVO)
│   └── coverage/
│       └── coverage_config.ini (NOVO)
├── scripts/
│   ├── vault-seed.sh (NOVO)
│   └── check_coverage.sh (NOVO)
└── .github/
    └── workflows/
        └── test-coverage.yml (NOVO)
```

---

## ✅ Checklist de Conclusão

Antes de considerar o epic completo:

- [ ] Todos os 9 tickets implementados
- [ ] Todos os testes passando (unitários + integração + smoke)
- [ ] Cobertura ≥70% em módulos críticos
- [ ] Zero credenciais hardcoded
- [ ] Smoke tests executando em <10min
- [ ] Scout Agents consumindo eventos reais
- [ ] CI/CD configurado com threshold de cobertura
- [ ] Documentação actualizada
- [ ] Relatório final criado

---

**Fim do Handoff**
