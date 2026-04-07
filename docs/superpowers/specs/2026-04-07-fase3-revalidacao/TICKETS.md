# Tickets Propostos — Fase 3: Revalidação de Superpoderes

> **Data:** 2026-04-07
> **Componentes Analisados:** 12
> **Total de Tickets:** 45
> **Prioridades:** ALTA (18), MÉDIA (17), BAIXA (10)

---

## Sumário por Prioridade

| Prioridade | Count | % |
|------------|-------|---|
| ALTA | 18 | 40% |
| MÉDIA | 17 | 38% |
| BAIXA | 10 | 22% |
| **TOTAL** | **45** | **100%** |

---

## Sumário por Componente

| Componente | ALTA | MÉDIA | BAIXA | Total |
|------------|------|-------|-------|-------|
| Self-Healing Core | 3 | 2 | 2 | 7 |
| Runbook Engine | 1 | 2 | 2 | 5 |
| Anomaly Detection | 4 | 1 | 1 | 6 |
| Proactive Prevention | 3 | 4 | 2 | 9 |
| SLO Tracking | 1 | 1 | 1 | 3 |
| Distributed Tracing | 0 | 0 | 0 | 0 |
| Explainability API | 0 | 1 | 3 | 4 |
| Governance Reports | 0 | 0 | 0 | 0 |
| Policy Engine | 0 | 2 | 1 | 3 |
| Risk Matrix | 1 | 0 | 2 | 3 |
| Chaos Engineering | 4 | 1 | 1 | 6 |
| Incident Timeline | 0 | 0 | 0 | 0 |

---

## Tickets por Prioridade

### ALTA Prioridade (18 tickets)

#### 1. FASE3-001: Corrigir import UTC em DetectionService
- **Tipo:** bug
- **Componente:** Self-Healing Core
- **Descrição:** Substituir `from neural_hive_domain import UTC` por `datetime.now(timezone.utc)`
- **Arquivos:** `services/self-healing-engine/src/services/detection_service.py`, `health_monitor.py`
- **Estimativa:** XS (1 hora)
- **Bloqueia:** Execução de todos os testes do Self-Healing

#### 2. FASE3-006: Corrigir testes com import errors
- **Tipo:** test
- **Componente:** Self-Healing Core
- **Descrição:** 26 testes falhando por import errors (UTC, fixtures)
- **Arquivos:** `services/self-healing-engine/tests/conftest.py`, `test_*.py`
- **Estimativa:** M (3-5 dias)
- **Bloqueia:** Validação completa do componente

#### 3. GAPS-04-01: Fix import UTC em detection_service (Runbook Engine)
- **Tipo:** bug
- **Componente:** Runbook Engine
- **Descrição:** Substituir `from neural_hive_domain import UTC` por `datetime.now(timezone.utc)`
- **Arquivos:** `services/self-healing-engine/src/services/detection_service.py`
- **Estimativa:** XS (5 minutos)
- **Bloqueia:** Execução de 14 testes do PlaybookExecutor

#### 4. FASE3-ANOMALY-001: Integrar HealthMonitor no DetectionService
- **Tipo:** feature
- **Componente:** Anomaly Detection
- **Descrição:** Criar methods `detect_kafka_lag()` e `detect_database_issues()` que delegam para HealthMonitor
- **Arquivos:** `services/self-healing-engine/src/services/detection_service.py`
- **Estimativa:** M (3-5 dias)
- **Impacto:** Completude de 64% → 85%

#### 5. FASE3-ANOMALY-002: Implementar Pod Crash Loop Detection
- **Tipo:** feature
- **Componente:** Anomaly Detection
- **Descrição:** Detectar pods com restartCount > 3 em 10 minutos, usando Kubernetes API
- **Arquivos:** `services/self-healing-engine/src/services/detection_service.py`
- **Estimativa:** L (1-2 semanas)
- **Impacto:** Completude de 64% → 85%

#### 6. FASE3-ANOMALY-003: Adicionar testes para deteções faltantes
- **Tipo:** test
- **Componente:** Anomaly Detection
- **Descrição:** Testes para `detect_kafka_lag()`, `detect_database_issues()`, `detect_pod_crash_loop()`
- **Arquivos:** `services/self-healing-engine/tests/test_detection_service.py`
- **Estimativa:** M (3-5 dias)
- **Impacto:** Cobertura de testes 60% → 80%

#### 7. FASE3-ANOMALY-004: Actualizar README para reflectir estado real
- **Tipo:** docs
- **Componente:** Anomaly Detection
- **Descrição:** README lista 5 deteções mas apenas 2 implementadas (64% completude)
- **Arquivos:** `services/self-healing-engine/README.md`
- **Estimativa:** S (2-3 dias)
- **Impacto:** Documentação fiel ao estado actual

#### 8. FASE3-PREV-001: Iniciar loop de detecção em produção
- **Tipo:** feature
- **Componente:** Proactive Prevention
- **Descrição:** Adicionar `run_detection_loop()` no startup do serviço (main.py)
- **Arquivos:** `services/self-healing-engine/src/main.py`
- **Estimativa:** S (2-3 dias)
- **Impacto:** Loop implementado mas não iniciado

#### 9. FASE3-PREV-002: Adicionar métricas do DetectionService
- **Tipo:** feature
- **Componente:** Proactive Prevention
- **Descrição:** Criar métricas `DETECTION_TOTAL` e `DETECTION_DURATION` (Prometheus)
- **Arquivos:** `services/self-healing-engine/src/services/detection_service.py`
- **Estimativa:** S (2-3 dias)
- **Impacto:** Impossível monitorar detecções em tempo real

#### 10. FASE3-PREV-003: Validação de playbooks antes da execução
- **Tipo:** feature
- **Componente:** Proactive Prevention
- **Descrição:** Adicionar flag `playbook_validated` no `RemediationTrigger` e verificar antes de executar
- **Arquivos:** `services/self-healing-engine/src/services/detection_service.py`, `models.py`
- **Estimativa:** M (3-5 dias)
- **Impacto:** Playbooks não testados podem ser executados automaticamente

#### 11. SLO-001: Corrigir bug de mapeamento CRD → Modelo
- **Tipo:** bug
- **Componente:** SLO Tracking
- **Descrição:** Atualizar linha 280-284 de `slo_manager.py` para mapear camelCase → snake_case em `SLIQuery`
- **Arquivos:** `services/sla-management-system/src/services/slo_manager.py`
- **Estimativa:** XS (5 minutos)
- **Impacto:** 3 testes falhando, sincronização de CRDs não funciona

#### 12. FASE3-CHAOS-001: Fixar import errors em injetores
- **Tipo:** bug
- **Componente:** Chaos Engineering
- **Descrição:** Adicionar exports em `src/chaos/injectors/__init__.py` para PodInjector, NetworkInjector, ResourceInjector, ApplicationInjector
- **Arquivos:** `services/self-healing-engine/src/chaos/injectors/__init__.py`
- **Estimativa:** S (2-3 dias)
- **Impacto:** 10 testes falhando por import errors

#### 13. FASE3-CHAOS-002: Fixar dependency issues (UTC import)
- **Tipo:** bug
- **Componente:** Chaos Engineering
- **Descrição:** Usar `datetime.timezone.utc` diretamente ou fixar export `UTC` em `neural_hive_domain`
- **Arquivos:** `services/self-healing-engine/src/chaos/`, tests
- **Estimativa:** S (2-3 dias)
- **Impacto:** Testes de validação de recovery falham

#### 14. FASE3-CHAOS-003: Fixar CircuitBreaker API
- **Tipo:** bug
- **Componente:** Chaos Engineering
- **Descrição:** Adicionar property `is_open` em `CircuitBreaker` (actualmente `_open` é privado)
- **Arquivos:** `services/self-healing-engine/src/services/circuit_breaker.py`
- **Estimativa:** XS (15 minutos)
- **Impacto:** Testes de circuit breaker falham

#### 15. FASE3-CHAOS-004: Fixar GameDayRunner constructor
- **Tipo:** bug
- **Componente:** Chaos Engineering
- **Descrição:** Remover parâmetro `playbook_executor` do teste ou adicionar ao construtor
- **Arquivos:** `services/self-healing-engine/src/chaos/game_day_runner.py`, tests
- **Estimativa:** XS (15 minutos)
- **Impacto:** Testes de Game Day falham

#### 16. RISK-001: Corrigir timezone issues
- **Tipo:** bug
- **Componente:** Risk Matrix
- **Descrição:** 28 testes falhando por datetime naive vs aware (usar `datetime.now(timezone.utc)`)
- **Arquivos:** `libraries/python/neural_hive_risk_scoring/risk_scoring/history.py`, `alerts.py`
- **Estimativa:** M (3-5 dias)
- **Impacto:** 90% → 100% de testes passando

#### 17. FASE3-PREV-004: Testes de PlaybookValidator
- **Tipo:** test
- **Componente:** Proactive Prevention
- **Descrição:** Criar suite de testes completa para PlaybookValidator (cobertura > 80%)
- **Arquivos:** `services/self-healing-engine/tests/test_playbook_validator.py`
- **Estimativa:** M (3-5 dias)
- **Impacto:** Validação proativa não testada

#### 18. FASE3-PREV-005: Testes de GameDayRunner
- **Tipo:** test
- **Componente:** Proactive Prevention
- **Descrição:** Testar CLI e comandos do GameDayRunner, mock ChaosEngine
- **Arquivos:** `services/self-healing-engine/tests/test_game_day_runner.py`
- **Estimativa:** M (3-5 dias)
- **Impacto:** CLI não testado

---

### MÉDIA Prioridade (17 tickets)

#### 19. FASE3-003: Adicionar métricas Prometheus missing
- **Tipo:** feature
- **Componente:** Self-Healing Core
- **Descrição:** Métricas para deadlocks, memory leaks, health checks, MTTR
- **Arquivos:** `services/self-healing-engine/src/services/detection_service.py`, `health_monitor.py`, `remediation_manager.py`
- **Estimativa:** M (1 semana)

#### 20. FASE3-005: Criar documentação de runbooks
- **Tipo:** docs
- **Componente:** Self-Healing Core
- **Descrição:** Documentar quando executar, o que faz, como verificar resultado, passos manuais
- **Arquivos:** `services/self-healing-engine/docs/RUNBOOKS.md`
- **Estimativa:** S (2-3 dias)

#### 21. GAPS-04-02: Implementar validação Pydantic para playbooks
- **Tipo:** feature
- **Componente:** Runbook Engine
- **Descrição:** Criar schema Pydantic para validar estrutura YAML de playbooks
- **Arquivos:** `services/self-healing-engine/src/services/playbook_executor.py`
- **Estimativa:** M (1 semana)

#### 22. GAPS-04-03: Criar testes E2E com kind/minikube
- **Tipo:** test
- **Componente:** Runbook Engine
- **Descrição:** Setup testes reais com Kubernetes cluster local (kind/minikube)
- **Arquivos:** `services/self-healing-engine/tests/integration/`
- **Estimativa:** L (1-2 semanas)

#### 23. FASE3-PREV-006: Histórico de memória em Redis
- **Tipo:** feature
- **Componente:** Proactive Prevention
- **Descrição:** Implementar cache distribuído para histórico de memória (perdido em restart)
- **Arquivos:** `services/self-healing-engine/src/services/detection_service.py`
- **Estimativa:** M (3-5 dias)

#### 24. FASE3-PREV-007: Testes E2E
- **Tipo:** test
- **Componente:** Proactive Prevention
- **Descrição:** Test com Docker Compose para validar fluxo completo
- **Arquivos:** `services/self-healing-engine/tests/integration/`
- **Estimativa:** L (1-2 semanas)

#### 25. FASE3-PREV-008: Producer Kafka para eventos
- **Tipo:** feature
- **Componente:** Proactive Prevention
- **Descrição:** Publicar eventos de detecção no Kafka para outros serviços
- **Arquivos:** `services/self-healing-engine/src/services/detection_service.py`
- **Estimativa:** M (3-5 dias)

#### 26. FASE3-PREV-009: Tracing distribuído
- **Tipo:** feature
- **Componente:** Proactive Prevention
- **Descrição:** Adicionar spans OpenTelemetry para detecções
- **Arquivos:** `services/self-healing-engine/src/services/detection_service.py`
- **Estimativa:** M (3-5 dias)

#### 27. SLO-002: Testes de Integração E2E
- **Tipo:** test
- **Componente:** SLO Tracking
- **Descrição:** Criar testes E2E com Prometheus mock e Kind cluster
- **Arquivos:** `services/sla-management-system/tests/integration/test_slo_manager_e2e.py`
- **Estimativa:** M (1 semana)

#### 28. EXPLAINABILITY-001: Aumentar coverage de testes
- **Tipo:** test
- **Componente:** Explainability API
- **Descrição:** Aumentar cobertura de 75-80% para 85%+
- **Arquivos:** `services/explainability-api/tests/`
- **Estimativa:** M (1 semana)

#### 29. POLICY-001: Testar 47 políticas Rego com dataset real
- **Tipo:** test
- **Componente:** Policy Engine
- **Descrição:** Criar testes Rego para todas as 47 políticas implementadas
- **Arquivos:** `opa/policies/test_*.rego`
- **Estimativa:** M (3-5 dias)

#### 30. POLICY-002: Documentar políticas de segurança
- **Tipo:** docs
- **Componente:** Policy Engine
- **Descrição:** Criar README para cada categoria de política com exemplos
- **Arquivos:** `opa/policies/README.md`
- **Estimativa:** S (2-3 dias)

#### 31. FASE3-CHAOS-005: Aumentar cobertura de testes
- **Tipo:** test
- **Componente:** Chaos Engineering
- **Descrição:** Actual 60% → Alvo 80%, foco em testes de integração E2E
- **Arquivos:** `services/self-healing-engine/tests/`
- **Estimativa:** L (1-2 semanas)

#### 32. FASE3-ANOMALY-005: Integrar no Detection Loop
- **Tipo:** feature
- **Componente:** Anomaly Detection
- **Descrição:** Adicionar checks de Kafka lag, DB issues e crash loop no `run_detection_loop()`
- **Arquivos:** `services/self-healing-engine/src/services/detection_service.py`
- **Estimativa:** M (3-5 dias)

#### 33. FASE3-PREV-010: Integração com Service Registry
- **Tipo:** feature
- **Componente:** Proactive Prevention
- **Descrição:** Descoberta dinâmica de workflows e pods (evitar hardcoded)
- **Arquivos:** `services/self-healing-engine/src/services/detection_service.py`
- **Estimativa:** L (1-2 semanas)

#### 34. FASE3-PREV-011: Integração com AlertManager
- **Tipo:** feature
- **Componente:** Proactive Prevention
- **Descrição:** Adicionar webhook integration para PagerDuty/Slack
- **Arquivos:** `services/self-healing-engine/src/services/detection_service.py`
- **Estimativa:** S (2-3 dias)

#### 35. FASE3-PREV-012: Testes de run_detection_loop
- **Tipo:** test
- **Componente:** Proactive Prevention
- **Descrição:** Test com mock de workflows e pods
- **Arquivos:** `services/self-healing-engine/tests/test_detection_service.py`
- **Estimativa:** S (2-3 dias)

---

### BAIXA Prioridade (10 tickets)

#### 36. FASE3-004: Adicionar tracing OTEL missing
- **Tipo:** feature
- **Componente:** Self-Healing Core
- **Descrição:** Spans OTEL para DetectionService, HealthMonitor, RemediationManager
- **Arquivos:** `services/self-healing-engine/src/services/*.py`
- **Estimativa:** S (2-3 dias)

#### 37. GAPS-04-04: Criar README de playbooks
- **Tipo:** docs
- **Componente:** Runbook Engine
- **Descrição:** Documentar como criar e usar playbooks customizados
- **Arquivos:** `services/self-healing-engine/docs/PLAYBOOKS.md`
- **Estimativa:** S (2-3 dias)

#### 38. GAPS-04-05: Padronizar nomenclatura YAML
- **Tipo:** refactor
- **Componente:** Runbook Engine
- **Descrição:** Unificar `steps` vs `actions` em todos os playbooks
- **Arquivos:** `services/self-healing-engine/playbooks/*.yaml`
- **Estimativa:** XS (1 hora)

#### 39. SLO-003: Dashboard de Monitorização
- **Tipo:** feature
- **Componente:** SLO Tracking
- **Descrição:** Criar dashboard Grafana para métricas `sla_crd_sync_*`
- **Arquivos:** `monitoring/dashboards/slo-sync-dashboard.json`
- **Estimativa:** S (2-3 dias)

#### 40. EXPLAINABILITY-002: Adicionar suite E2E
- **Tipo:** test
- **Componente:** Explainability API
- **Descrição:** Testes E2E completos para Explainability API v3
- **Arquivos:** `services/explainability-api/tests/e2e/`
- **Estimativa:** L (1-2 semanas)

#### 41. EXPLAINABILITY-003: Completar documentação OpenAPI/Swagger
- **Tipo:** docs
- **Componente:** Explainability API
- **Descrição:** Documentação completa da API v3
- **Arquivos:** `services/explainability-api/docs/openapi.yaml`
- **Estimativa:** M (3-5 dias)

#### 42. EXPLAINABILITY-004: Implementar caching para performance
- **Tipo:** feature
- **Componente:** Explainability API
- **Descrição:** Cache de explicações frequentes
- **Arquivos:** `services/explainability-api/src/services/shap_calculator.py`
- **Estimativa:** M (3-5 dias)

#### 43. POLICY-003: Versionamento avançado de políticas
- **Tipo:** feature
- **Componente:** Policy Engine
- **Descrição:** Implementar versionamento de políticas (actualmente apenas revision ID básico)
- **Arquivos:** `opa/policies/`
- **Estimativa:** L (1-2 semanas)

#### 44. RISK-002: Adicionar cobertura de testes E2E
- **Tipo:** test
- **Componente:** Risk Matrix
- **Descrição:** Testes E2E com Docker Compose
- **Arquivos:** `libraries/python/neural_hive_risk_scoring/tests/e2e/`
- **Estimativa:** M (1 semana)

#### 45. RISK-003: Integração com dashboard Grafana
- **Tipo:** feature
- **Componente:** Risk Matrix
- **Descrição:** Dashboard para visualização de risk scores
- **Arquivos:** `monitoring/dashboards/risk-matrix-dashboard.json`
- **Estimativa:** S (2-3 dias)

---

## Análise Consolidada

### Tickets por Tipo

| Tipo | Count | % |
|------|-------|---|
| bug | 8 | 18% |
| feature | 17 | 38% |
| test | 12 | 27% |
| docs | 6 | 13% |
| refactor | 2 | 4% |
| **TOTAL** | **45** | **100%** |

### Tickets por Componente (Top 5)

1. **Proactive Prevention:** 9 tickets (20%)
2. **Chaos Engineering:** 6 tickets (13%)
3. **Anomaly Detection:** 6 tickets (13%)
4. **Self-Healing Core:** 7 tickets (16%)
5. **Runbook Engine:** 5 tickets (11%)

### Estimativa de Esforço Total

| Prioridade | Count | Esforço Total | Tempo Estimado |
|------------|-------|---------------|----------------|
| ALTA | 18 | XS(5) + S(12) + M(9) + L(2) | ~6-8 semanas |
| MÉDIA | 17 | S(6) + M(10) + L(4) | ~8-10 semanas |
| BAIXA | 10 | XS(1) + S(5) + M(3) + L(2) | ~3-4 semanas |
| **TOTAL** | **45** | - | **~17-22 semanas** |

### Gaps Críticos Blocantes (8)

1. **Import UTC** (4 tickets) - Bloqueia testes em Self-Healing, Runbook, Chaos, Risk
2. **Import errors em injetores** (1 ticket) - Bloqueia testes Chaos
3. **Bug mapeamento CRD** (1 ticket) - Bloqueia sync SLO
4. **CircuitBreaker API** (1 ticket) - Bloqueia testes Chaos
5. **GameDayRunner constructor** (1 ticket) - Bloqueia testes Chaos

**Resolução estimada:** 1-2 semanas (prioridade máxima)

---

## Recomendações de Execução

### Fase 1: Críticos (1-2 semanas)
- Resolver todos os 8 gaps críticos blocantes
- Meta: Desbloquear execução de testes em todos os componentes

### Fase 2: Alta Prioridade (3-4 semanas)
- Completar tickets ALTA restantes (10)
- Meta: 100% de testes passando

### Fase 3: Média Prioridade (6-8 semanas)
- Completar tickets MÉDIA (17)
- Meta: Melhorar cobertura e funcionalidades

### Fase 4: Baixa Prioridade (3-4 semanas)
- Completar tickets BAIXA (10)
- Meta: Polimento e documentação

---

**Relatório gerado:** 2026-04-07
**Análise:** 12 specs de revalidação da Fase 3
**Status:** ✅ Tickets consolidados e priorizados
