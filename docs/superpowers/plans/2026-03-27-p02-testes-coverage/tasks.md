# Spec Tasks — P02 Testes Coverage

## Tasks

- [x] 1. Baseline de cobertura
  - [x] 1.1 Instalar pytest-cov
  - [x] 1.2 Rodar coverage para todos os módulos
  - [x] 1.3 Gerar baseline report
  - [x] 1.4 Identificar funções sem cobertura

- [x] 2. Testes para drift_monitoring (0% → 70%)
  - [x] 2.1 Escrever testes para DriftDetector
  - [x] 2.2 Escrever testes para DataDriftAnalyzer
  - [x] 2.3 Escrever testes para ModelDriftAnalyzer
  - [x] 2.4 Verificar cobertura ≥ 70%

- [ ] 3. Testes para observability (0% → 70%)
  - [x] 3.1 Escrever testes para Tracer
  - [x] 3.2 Escrever testes para MetricsCollector
  - [ ] 3.3 Escrever testes para Logger
  - [ ] 3.4 Verificar cobertura ≥ 70% (58% atual)

- [x] 4. Testes para compliance (13% → 70%)
  - [x] 4.1 Escrever testes para PIIDetector
  - [x] 4.2 Escrever testes para PIIMasker
  - [x] 4.3 Escrever testes para ComplianceChecker
  - [x] 4.4 Verificar cobertura ≥ 70%

- [x] 5. Testes para semantic_pipeline (15% → 70%)
  - [x] 5.1 Escrever testes para SemanticParser
  - [x] 5.2 Escrever testes para DAGGenerator
  - [x] 5.3 Escrever testes para RiskScorer
  - [x] 5.4 Verificar cobertura ≥ 70%

- [ ] 6. Testes para feedback (21% → 70%)
  - [x] 6.1 Escrever testes para FeedbackCollector
  - [x] 6.2 Escrever testes para ActiveLearning
  - [x] 6.3 Escrever testes para BalanceAnalyzer
  - [ ] 6.4 Verificar cobertura ≥ 70% (60% atual)

- [x] 7. Testes para explainability (21% → 70%)
  - [x] 7.1 Escrever testes para ExplainabilityGenerator
  - [x] 7.2 Escrever testes para NarrativeBuilder
  - [x] 7.3 Verificar cobertura ≥ 70%

- [ ] 8. Testes E2E
  - [ ] 8.1 Analisar e2e-tests.yml.disabled
  - [ ] 8.2 Dividir em 6 suites menores
  - [ ] 8.3 Criar e2e-suite-01-gateway.yml
  - [ ] 8.4 Criar e2e-suite-02-cognitive.yml
  - [ ] 8.5 Criar e2e-suite-03-consensus.yml
  - [ ] 8.6 Criar e2e-suite-04-orchestrator.yml
  - [ ] 8.7 Criar e2e-suite-05-agents.yml
  - [ ] 8.8 Criar e2e-suite-06-full.yml

- [ ] 9. Mutation testing
  - [ ] 9.1 Instalar mutmut
  - [ ] 9.2 Configurar mutmut para projeto
  - [ ] 9.3 Rodar mutation test baseline
  - [ ] 9.4 Documentar resultados

- [x] 10. Relatório final
  - [x] 10.1 Gerar coverage report final
  - [x] 10.2 Criar gráfico de evolução
  - [x] 10.3 Documentar modules restantes
  - [ ] 10.4 Commit e push

## Resumo

**Módulos com ≥ 70%:**
- semantic_pipeline: 90% ✅
- compliance: 72% ✅
- drift_monitoring: 75% ✅
- explainability: 89% ✅

**Módulos abaixo de 70%:**
- observability: 58% (faltam 12%)
- feedback: 60% (faltam 10%)

**Média dos 6 módulos:** 72.3%
