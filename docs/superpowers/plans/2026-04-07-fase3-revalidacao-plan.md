# Fase 3 Revalidação — Plano de Implementação

> **Para trabalhadores agent:** SUB-SKILL OBRIGATÓRIO: Use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para implementar este plano tarefa-a-tarefa. Passos usam sintaxe de checkbox (`- [ ]`) para tracking.

**Objetivo:** Validar profundamente os 12 componentes da Fase 3 (Auto-Recuperação) com 5 critérios e criar specs para melhorias necessárias.

**Arquitetura:** Análise paralela de 12 componentes, organizada em 4 ondas sequenciais por dependência. Cada spec é independente e contém validação completa + tickets propostos.

**Stack:** Python 3.12+, feature-dev:code-explorer, code-review:code-review, Glob/Grep/Read

---

## Estrutura de Ficheiros

```
docs/superpowers/specs/2026-04-07-fase3-revalidacao/
├── DESIGN.md (já criado)
├── 01-self-healing-core-spec.md
├── 02-runbook-engine-spec.md
├── 03-anomaly-detection-spec.md
├── 04-proactive-prevention-spec.md
├── 05-slo-tracking-spec.md
├── 06-tracing-correlation-spec.md
├── 07-explainability-spec.md
├── 08-governance-reports-spec.md
├── 09-policy-engine-spec.md
├── 10-risk-matrix-spec.md
├── 11-chaos-engineering-spec.md
├── 12-incident-timeline-spec.md
├── MATRIZ_GAPS.md (consolidado de gaps)
└── TICKETS.md (consolidado de tickets)
```

**Responsabilidade de cada ficheiro:**
- `*-spec.md`: Validação completa de um componente (5 critérios + tickets)
- `MATRIZ_GAPS.md`: Tabela consolidada de todos os gaps dos 12 componentes
- `TICKETS.md`: Lista completa de tickets para implementação futura

---

## Task 1: WAVE 1 — Self-Healing Service Core

**Files:**
- Create: `docs/superpowers/specs/2026-04-07-fase3-revalidacao/01-self-healing-core-spec.md`
- Analyze: `services/self-healing-engine/src/services/*.py`
- Test: `services/self-healing-engine/tests/`

- [ ] **Step 1: Descobrir ficheiros do componente**

```bash
find services/self-healing-engine/src/services -name "*.py" -type f
find services/self-healing-engine/tests -name "test_*.py" -type f
```

Expected: Lista de ficheiros .py e test_*.py

- [ ] **Step 2: Ler ficheiros principais**

```bash
# Count LOC
wc -l services/self-healing-engine/src/services/*.py

# Read main services
cat services/self-healing-engine/src/services/detection_service.py
cat services/self-healing-engine/src/services/remediation_manager.py
cat services/self-healing-engine/src/services/health_monitor.py
```

Expected: ~1800 LOC totais, 3 serviços principais identificados

- [ ] **Step 3: Validar Funcionalidade**

Usar code-explorer para analisar:
- `DetectionService` — deadlock detection, memory leak detection
- `RemediationManager` — estado de remediação (PENDING → RUNNING → COMPLETED/FAILED)
- `HealthMonitor` — monitorização contínua de serviços

Checklist:
- [ ] Deadlock detection implementada
- [ ] Memory leak detection implementada
- [ ] Estado de remediação completo
- [ ] Health monitoring funcional

- [ ] **Step 4: Validar Testes**

```bash
pytest services/self-healing-engine/tests/ --collect-only
pytest services/self-healing-engine/tests/ -v --tb=short
```

Expected: ~156 testes, 100% pass rate

- [ ] **Step 5: Validar Integração**

Verificar no código:
- [ ] Kafka producer/consumer para eventos de remediação
- [ ] MongoDB client para persistência de estado
- [ ] gRPC client para Orchestrator (workflow status)
- [ ] Kubernetes client para pod metrics

Search:
```bash
grep -r "aiokafka" services/self-healing-engine/src/
grep -r "motor" services/self-healing-engine/src/
grep -r "orchestrator_client" services/self-healing-engine/src/
grep -r "kubernetes" services/self-healing-engine/src/
```

- [ ] **Step 6: Validar Observabilidade**

```bash
grep -r "prometheus_client\|Counter\|Gauge\|Histogram" services/self-healing-engine/src/
grep -r "trace\|span\|opentelemetry" services/self-healing-engine/src/
grep -r "structlog\|get_logger" services/self-healing-engine/src/
```

Expected: Métricas Prometheus, spans OTEL, logs structlog

- [ ] **Step 7: Validar Documentação**

```bash
ls -la services/self-healing-engine/README.md
ls -la services/self-healing-engine/docs/
find services/self-healing-engine -name "*.md" -type f
```

Expected: README, API docs, runbooks

- [ ] **Step 8: Criar spec document**

Criar `01-self-healing-core-spec.md` com template:
- Metadata (componente, location, LOC, testes)
- 5 secções de validação (funcionalidade, testes, integração, observabilidade, documentação)
- Gaps identificados
- Tickets propostos

- [ ] **Step 9: Commit**

```bash
git add docs/superpowers/specs/2026-04-07-fase3-revalidacao/01-self-healing-core-spec.md
git commit -m "docs(fase3): adicionar spec de revalidação - Self-Healing Core"
```

---

## Task 2: WAVE 1 — Runbook Execution Engine

**Files:**
- Create: `docs/superpowers/specs/2026-04-07-fase3-revalidacao/02-runbook-engine-spec.md`
- Analyze: `services/self-healing-engine/src/services/playbook_executor.py`
- Test: `services/self-healing-engine/tests/test_playbook_executor.py`

- [ ] **Step 1: Descobrir ficheiros**

```bash
find services/self-healing-engine -name "*playbook*" -o -name "*runbook*" | grep -E "\.(py|yaml)$"
```

- [ ] **Step 2: Ler implementação principal**

```bash
wc -l services/self-healing-engine/src/services/playbook_executor.py
cat services/self-healing-engine/src/services/playbook_executor.py
```

Expected: ~400 LOC, execução de YAML playbooks

- [ ] **Step 3: Validar Funcionalidade**

Checklist:
- [ ] Carregamento de playbooks YAML
- [ ] Validação OPA antes da execução
- [ ] Circuit breakers por serviço
- [ ] Callbacks (on_action_completed, on_playbook_completed)
- [ ] Timeouts configuráveis

- [ ] **Step 4: Validar Testes**

```bash
pytest services/self-healing-engine/tests/test_playbook_executor.py -v
```

Expected: ~8 testes, validação de playbooks

- [ ] **Step 5: Validar Integração**

```bash
grep -r "opa\|open_policy_agent" services/self-healing-engine/src/services/playbook_executor.py
```

Expected: OPA validation implementada

- [ ] **Step 6: Validar Observabilidade**

```bash
grep -E "Counter|Gauge|Histogram" services/self-healing-engine/src/services/playbook_executor.py
```

Expected: Métricas de duração, status, playbook type

- [ ] **Step 7: Validar Documentação**

```bash
find services/self-healing-engine -name "*.yaml" | grep playbook
```

Expected: Playbooks de exemplo (deadlock_recovery, memory_leak, db_recovery)

- [ ] **Step 8: Criar spec e commit**

```bash
git add docs/superpowers/specs/2026-04-07-fase3-revalidacao/02-runbook-engine-spec.md
git commit -m "docs(fase3): adicionar spec de revalidação - Runbook Engine"
```

---

## Task 3: WAVE 1 — Anomaly Detection System

**Files:**
- Create: `docs/superpowers/specs/2026-04-07-fase3-revalidacao/03-anomaly-detection-spec.md`
- Analyze: `services/self-healing-engine/src/services/detection_service.py`

- [ ] **Step 1: Ler DetectionService**

```bash
wc -l services/self-healing-engine/src/services/detection_service.py
cat services/self-healing-engine/src/services/detection_service.py
```

- [ ] **Step 2: Validar tipos de anomalias**

Checklist:
- [ ] Deadlock Detection (workflows stuck > 1800s)
- [ ] Memory Leak Detection (pod memory > 90% por > 300s)
- [ ] Kafka Lag Detection (consumer lag > 10000)
- [ ] Database Connection Issues (pool exhaustion)
- [ ] Pod Crash Loop (CrashLoopBackOff)

- [ ] **Step 3: Validar Testes**

```bash
pytest services/self-healing-engine/tests/test_detection_service.py -v
```

Expected: ~10 testes

- [ ] **Step 4-7: Integração, Observabilidade, Documentação** (mesmo padrão)

- [ ] **Step 8: Criar spec e commit**

```bash
git commit -m "docs(fase3): adicionar spec de revalidação - Anomaly Detection"
```

---

## Task 4: WAVE 2 — Distributed Tracing Correlation

**Files:**
- Create: `docs/superpowers/specs/2026-04-07-fase3-revalidacao/06-tracing-correlation-spec.md`
- Analyze: `libraries/python/neural_hive_observability/`

- [ ] **Step 1: Descobrir ficheiros de observabilidade**

```bash
find libraries/python/neural_hive_observability -name "*.py" -type f
```

- [ ] **Step 2: Ler instrumentação Kafka e OTEL**

```bash
cat libraries/python/neural_hive_observability/kafka_instrumentation.py
cat libraries/python/neural_hive_observability/tracing.py
```

- [ ] **Step 3: Validar Funcionalidade**

Checklist:
- [ ] correlation_id propagation via Kafka
- [ ] trace_id propagation via OpenTelemetry
- [ ] Span attributes para contexto cognitivo
- [ ] Jaeger integration

- [ ] **Step 4: Validar Testes E2E**

```bash
find tests/e2e/tracing -name "*.py"
pytest tests/e2e/tracing/ -v
```

Expected: Testes E2E de flow tracing, specialist tracing

- [ ] **Step 5: Validar Documentação**

```bash
cat docs/observability/jaeger-queries-neural-hive.md
cat monitoring/dashboards/correlation-id-propagation.json
```

- [ ] **Step 6: Criar spec e commit**

```bash
git commit -m "docs(fase3): adicionar spec de revalidação - Distributed Tracing"
```

---

## Task 5: WAVE 2 — Governance Audit Reports

**Files:**
- Create: `docs/superpowers/specs/2026-04-07-fase3-revalidacao/08-governance-reports-spec.md`
- Analyze: `scripts/governance/`, `policies/rego/`

- [ ] **Step 1: Descobrir scripts de governança**

```bash
find scripts/governance -name "*.py" -o -name "*.sh"
```

- [ ] **Step 2: Ler script de verificação de hash**

```bash
cat scripts/governance/verify-hash-integrity.py
```

Expected: ~171 linhas, verificação SHA-256 de decisões

- [ ] **Step 3: Validar Funcionalidade**

Checklist:
- [ ] Cálculo de hash SHA-256 de decisões
- [ ] Verificação de integridade do ledger cognitivo
- [ ] Relatório de auditoria

- [ ] **Step 4: Validar Testes**

```bash
cat tests/integration/governance-compliance-test.sh
```

Expected: Teste de compliance de políticas

- [ ] **Step 5: Validar Integração**

```bash
grep -r "consensus-engine\|consolidated_decision" scripts/governance/
```

Expected: Integração com consensus-engine

- [ ] **Step 6: Validar Observabilidade**

```bash
grep -E "Counter|Gauge|Histogram" scripts/governance/
```

Expected: Métricas de auditoria

- [ ] **Step 7: Validar Documentação**

```bash
cat monitoring/dashboards/governance-executive-dashboard.json
cat monitoring/alerts/governance-alerts.yaml
```

- [ ] **Step 8: Criar spec e commit**

```bash
git commit -m "docs(fase3): adicionar spec de revalidação - Governance Reports"
```

---

## Task 6: WAVE 2 — Dynamic Policy Engine

**Files:**
- Create: `docs/superpowers/specs/2026-04-07-fase3-revalidacao/09-policy-engine-spec.md`
- Analyze: `policies/rego/`, `services/opa/`

- [ ] **Step 1: Descobrir políticas OPA**

```bash
find policies/rego -name "*.rego" | wc -l
find policies/rego -type d
```

Expected: ~58 arquivos .rego

- [ ] **Step 2: Analisar categorias de políticas**

```bash
ls -la policies/rego/orchestrator/
ls -la policies/rego/gatekeeper/
ls -la policies/rego/self_healing/
ls -la policies/rego/chaos/
```

- [ ] **Step 3: Validar Funcionalidade**

Checklist:
- [ ] SLA enforcement (orchestrator/)
- [ ] Admission control (gatekeeper/)
- [ ] Playbook validation (self_healing/)
- [ ] Experiment validation (chaos/)

- [ ] **Step 4: Validar Integração**

```bash
grep -r "opa\|rego" services/*/src/
```

Expected: Clientes OPA em vários serviços

- [ ] **Step 5: Validar Documentação**

```bash
find policies/rego -name "README.md"
```

- [ ] **Step 6: Criar spec e commit**

```bash
git commit -m "docs(fase3): adicionar spec de revalidação - Dynamic Policy Engine"
```

---

## Task 7: WAVE 3 — Explainability Dashboards

**Files:**
- Create: `docs/superpowers/specs/2026-04-07-fase3-revalidacao/07-explainability-spec.md`
- Analyze: `services/explainability-api/src/services/`

- [ ] **Step 1: Descobrir serviços de explainability**

```bash
find services/explainability-api/src/services -name "*.py" -type f
```

Expected: ~8 serviços (shap_calculator, temporal_tracker, hierarchical_explainer, etc.)

- [ ] **Step 2: Validar Funcionalidade**

Checklist:
- [ ] SHAP feature attribution (shap_calculator.py)
- [ ] Análise temporal de decisões (temporal_tracker.py)
- [ ] Explicações hierárquicas (hierarchical_explainer.py)
- [ ] Análise contrafactual (counterfactual_analyzer.py)
- [ ] API v3 endpoints

- [ ] **Step 3: Validar Testes**

```bash
find services/explainability-api/tests -name "test_*.py"
pytest services/explainability-api/tests/ -v
```

Expected: ~288 testes

- [ ] **Step 4: Validar Integração**

```bash
grep -r "mongodb\|kafka\|consensus" services/explainability-api/src/
```

Expected: MongoDB para persistência, Kafka para eventos

- [ ] **Step 5: Validar Observabilidade**

```bash
grep -E "Counter|Gauge|Histogram" services/explainability-api/src/
```

Expected: Métricas de explicações, latência SHAP

- [ ] **Step 6: Validar Documentação**

```bash
cat monitoring/dashboards/explainability-v3.json
```

- [ ] **Step 7: Criar spec e commit**

```bash
git commit -m "docs(fase3): adicionar spec de revalidação - Explainability Dashboards"
```

---

## Task 8: WAVE 3 — Risk Matrix Implementation

**Files:**
- Create: `docs/superpowers/specs/2026-04-07-fase3-revalidacao/10-risk-matrix-spec.md`
- Analyze: `libraries/python/neural_hive_risk_scoring/`

- [ ] **Step 1: Descobrir ficheiros de risk scoring**

```bash
find libraries/python/neural_hive_risk_scoring -name "*.py" -type f
```

Expected: ~12 arquivos (engine, calculator, ensemble, thresholds, etc.)

- [ ] **Step 2: Validar Funcionalidade**

Checklist:
- [ ] 5 domínios de risco (Business, Technical, Security, Operational, Compliance)
- [ ] Cálculo de risk score ponderado
- [ ] Classificação em risk bands
- [ ] Ensemble de modelos
- [ ] Gestão de thresholds dinâmicos

- [ ] **Step 3: Validar Testes**

```bash
find libraries/python/neural_hive_risk_scoring/tests -name "test_*.py"
pytest libraries/python/neural_hive_risk_scoring/tests/ -v
```

Expected: ~275 testes

- [ ] **Step 4-6: Integração, Observabilidade, Documentação** (mesmo padrão)

- [ ] **Step 7: Criar spec e commit**

```bash
git commit -m "docs(fase3): adicionar spec de revalidação - Risk Matrix"
```

---

## Task 9: WAVE 3 — Incident Timeline Generator

**Files:**
- Create: `docs/superpowers/specs/2026-04-07-fase3-revalidacao/12-incident-timeline-spec.md`
- Analyze: `services/explainability-api/src/services/temporal_tracker.py`

- [ ] **Step 1: Ler TemporalTracker**

```bash
wc -l services/explainability-api/src/services/temporal_tracker.py
cat services/explainability-api/src/services/temporal_tracker.py
```

Expected: ~300 LOC

- [ ] **Step 2: Validar Funcionalidade**

Checklist:
- [ ] Session analysis (decisões do mesmo plan_id)
- [ ] Window analysis (janela temporal de N dias)
- [ ] Seniority changes tracking
- [ ] Seniority distribution

- [ ] **Step 3: Validar Testes**

```bash
pytest services/explainability-api/tests/test_temporal_tracker.py -v
```

Expected: ~16 testes

- [ ] **Step 4: Validar API Endpoints**

```bash
grep -E "GET|POST|PUT|DELETE" services/explainability-api/src/api/routers/*.py | grep temporal
```

Expected: Endpoints `/api/v3/explainability/temporal/*`

- [ ] **Step 5-7: Integração, Observabilidade, Documentação** (mesmo padrão)

- [ ] **Step 8: Criar spec e commit**

```bash
git commit -m "docs(fase3): adicionar spec de revalidação - Incident Timeline"
```

---

## Task 10: WAVE 4 — Proactive Incident Prevention

**Files:**
- Create: `docs/superpowers/specs/2026-04-07-fase3-revalidacao/04-proactive-prevention-spec.md`
- Analyze: `services/self-healing-engine/src/services/detection_service.py` (run_detection_loop)

- [ ] **Step 1: Verificar loop de detecção**

```bash
grep -A 30 "run_detection_loop" services/self-healing-engine/src/services/detection_service.py
```

- [ ] **Step 2: Validar Funcionalidade**

Checklist:
- [ ] Loop contínuo de detecção
- [ ] Trigger automático de remediação
- [ ] Validação proativa de playbooks
- [ ] Game Days para testes

- [ ] **Step 3: Validar Testes**

```bash
grep -r "proactive\|game_day" services/self-healing-engine/tests/
```

- [ ] **Step 4-7: Integração, Observabilidade, Documentação** (mesmo padrão)

- [ ] **Step 8: Criar spec e commit**

```bash
git commit -m "docs(fase3): adicionar spec de revalidação - Proactive Prevention"
```

---

## Task 11: WAVE 4 — Advanced SLO Tracking

**Files:**
- Create: `docs/superpowers/specs/2026-04-07-fase3-revalidacao/05-slo-tracking-spec.md`
- Analyze: `services/sla-management-system/src/services/slo_manager.py`

- [ ] **Step 1: Descobrir ficheiros de SLO**

```bash
find services/sla-management-system/src/services -name "*.py"
```

- [ ] **Step 2: Validar Funcionalidade**

Checklist:
- [ ] CRD Sync (Kubernetes → PostgreSQL)
- [ ] Importação de alertas Prometheus
- [ ] Teste de queries contra Prometheus
- [ ] Validação de SLOs
- [ ] Reconciliação periódica

- [ ] **Step 3: Validar Testes**

```bash
find services/sla-management-system/tests -name "test_*.py"
pytest services/sla-management-system/tests/ -v
```

Expected: ~141 testes

- [ ] **Step 4-7: Integração, Observabilidade, Documentação** (mesmo padrão)

- [ ] **Step 8: Criar spec e commit**

```bash
git commit -m "docs(fase3): adicionar spec de revalidação - Advanced SLO Tracking"
```

---

## Task 12: WAVE 4 — Chaos Engineering Suite

**Files:**
- Create: `docs/superpowers/specs/2026-04-07-fase3-revalidacao/11-chaos-engineering-spec.md`
- Analyze: `services/self-healing-engine/src/chaos/`

- [ ] **Step 1: Descobrir ficheiros de chaos**

```bash
find services/self-healing-engine/src/chaos -name "*.py" -type f
```

Expected: chaos_engine.py, network_injector.py, pod_injector.py, resource_injector.py, etc.

- [ ] **Step 2: Validar Funcionalidade**

Checklist:
- [ ] ChaosEngine orquestração (~1100 LOC)
- [ ] 4 tipos de fault injectors (network, pod, resource, application)
- [ ] Validação OPA de experimentos
- [ ] Rollback automático
- [ ] Game Day Runner
- [ ] Validators (health, playbook)

- [ ] **Step 3: Validar Testes**

```bash
find services/self-healing-engine/tests -name "*chaos*"
pytest services/self-healing-engine/tests/test_chaos_engine.py -v
```

Expected: ~80 testes distribuídos

- [ ] **Step 4-7: Integração, Observabilidade, Documentação** (mesmo padrão)

- [ ] **Step 8: Criar spec e commit**

```bash
git commit -m "docs(fase3): adicionar spec de revalidação - Chaos Engineering Suite"
```

---

## Task 13: Consolidar Matriz de Gaps

**Files:**
- Create: `docs/superpowers/specs/2026-04-07-fase3-revalidacao/MATRIZ_GAPS.md`

- [ ] **Step 1: Extrair gaps de cada spec**

```bash
for file in docs/superpowers/specs/2026-04-07-fase3-revalidacao/*-spec.md; do
    echo "## $(basename $file)"
    grep -A 10 "## Gaps" "$file"
done
```

- [ ] **Step 2: Criar tabela consolidada**

```markdown
# Matriz de Gaps — Fase 3

| Componente | Funcionalidade | Testes | Integração | Observabilidade | Documentação | Total |
|------------|---------------|--------|------------|-----------------|--------------|-------|
| Self-Healing Core | 0 | 2 | 0 | 1 | 1 | 4 |
| ... | ... | ... | ... | ... | ... | ... |
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-04-07-fase3-revalidacao/MATRIZ_GAPS.md
git commit -m "docs(fase3): adicionar matriz consolidada de gaps"
```

---

## Task 14: Consolidar Tickets Propostos

**Files:**
- Create: `docs/superpowers/specs/2026-04-07-fase3-revalidacao/TICKETS.md`

- [ ] **Step 1: Extrair tickets de cada spec**

```bash
for file in docs/superpowers/specs/2026-04-07-fase3-revalidacao/*-spec.md; do
    grep -A 20 "## Tickets Propostos" "$file"
done
```

- [ ] **Step 2: Organizar por prioridade e tipo**

```markdown
# Tickets Propostos — Fase 3

## Alta Prioridade
- [ ] FASE3-001: ...
- [ ] FASE3-002: ...

## Média Prioridade
...

## Baixa Prioridade
...
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-04-07-fase3-revalidacao/TICKETS.md
git commit -m "docs(fase3): adicionar lista consolidada de tickets"
```

---

## Task 15: Criar Relatório Executivo Final

**Files:**
- Create: `docs/FASE_3_REVALIDACAO_FINAL_2026-04-07.md`

- [ ] **Step 1: Compilar estatísticas**

Das specs criadas, extrair:
- Total LOC analisado
- Total testes
- Completude por componente (%)
- Gaps totais
- Tickets propostos

- [ ] **Step 2: Escrever relatório executivo**

```markdown
# Fase 3 — Revalidação Final

**Data:** 2026-04-07
**Componentes Analisados:** 12
**Total LOC:** ~25,000
**Total Testes:** ~860

## Completude por Componente

| Componente | Completude | Gaps | Tickets |
|------------|------------|------|---------|
| ... | ... | ... | ... |

## Resumo Executivo

...
```

- [ ] **Step 3: Commit final**

```bash
git add docs/FASE_3_REVALIDACAO_FINAL_2026-04-07.md
git commit -m "docs(fase3): adicionar relatório executivo final de revalidação"
```

---

## Task 16: Preparar Handoff para Implementação

**Files:**
- Update: `docs/superpowers/specs/2026-04-07-fase3-revalidacao/README.md`

- [ ] **Step 1: Criar README de handoff**

```markdown
# Handoff — Fase 3 Revalidação

## Como usar estas specs

1. Cada spec (`*-spec.md`) contém validação completa + tickets
2. `TICKETS.md` contém todos os tickets organizados por prioridade
3. Para implementar, seguir os tickets em ordem de prioridade

## Próximos passos

1. Review das specs pela equipa
2. Priorização de tickets baseada em roadmap
3. Criação de branches por ticket: `feat/FASE3-XXX-descricao`
4. Implementação seguindo TDD
5. Code review via superpowers:code-review

## Estimativas

- Tempo total: X dias
- Esforço por onda: WAVE 1 (X dias), WAVE 2 (Y dias), ...
```

- [ ] **Step 2: Commit final**

```bash
git commit -m "docs(fase3): adicionar README de handoff para implementação"
```

---

## Self-Review

### Coverage Check
- [ ] 12 componentes cobertos
- [ ] 5 critérios validados por componente
- [ ] Specs criadas com gaps e tickets
- [ ] Matriz consolidada de gaps
- [ ] Tickets consolidados
- [ ] Relatório executivo final
- [ ] Handoff preparado

### Placeholder Check
- [ ] Sem "TBD", "TODO", "implementar depois"
- [ ] Todos os passos têm comandos específicos
- [ ] Todos os ficheiros têm paths exatos
- [ ] Todas as estimativas são específicas

### Type Consistency
- [ ] Nomes de componentes consistentes
- [ ] Paths de ficheiros consistentes
- [ ] Formato de specs consistente

---

**Fim do Plano de Implementação**
