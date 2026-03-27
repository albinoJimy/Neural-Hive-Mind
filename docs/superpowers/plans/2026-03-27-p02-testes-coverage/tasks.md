# Spec Tasks — P02 Testes Coverage

## Tasks

- [ ] 1. Baseline de cobertura
  - [ ] 1.1 Instalar pytest-cov
  - [ ] 1.2 Rodar coverage para todos os módulos
  - [ ] 1.3 Gerar baseline report
  - [ ] 1.4 Identificar funções sem cobertura

- [ ] 2. Testes para drift_monitoring (0% → 70%)
  - [ ] 2.1 Escrever testes para DriftDetector
  - [ ] 2.2 Escrever testes para DataDriftAnalyzer
  - [ ] 2.3 Escrever testes para ModelDriftAnalyzer
  - [ ] 2.4 Verificar cobertura ≥ 70%

- [ ] 3. Testes para observability (0% → 70%)
  - [ ] 3.1 Escrever testes para Tracer
  - [ ] 3.2 Escrever testes para MetricsCollector
  - [ ] 3.3 Escrever testes para Logger
  - [ ] 3.4 Verificar cobertura ≥ 70%

- [ ] 4. Testes para compliance (13% → 70%)
  - [ ] 4.1 Escrever testes para PIIDetector
  - [ ] 4.2 Escrever testes para PIIMasker
  - [ ] 4.3 Escrever testes para ComplianceChecker
  - [ ] 4.4 Verificar cobertura ≥ 70%

- [ ] 5. Testes para semantic_pipeline (15% → 70%)
  - [ ] 5.1 Escrever testes para SemanticParser
  - [ ] 5.2 Escrever testes para DAGGenerator
  - [ ] 5.3 Escrever testes para RiskScorer
  - [ ] 5.4 Verificar cobertura ≥ 70%

- [ ] 6. Testes para feedback (21% → 70%)
  - [ ] 6.1 Escrever testes para FeedbackCollector
  - [ ] 6.2 Escrever testes para ActiveLearning
  - [ ] 6.3 Escrever testes para BalanceAnalyzer
  - [ ] 6.4 Verificar cobertura ≥ 70%

- [ ] 7. Testes para explainability (21% → 70%)
  - [ ] 7.1 Escrever testes para ExplainabilityGenerator
  - [ ] 7.2 Escrever testes para NarrativeBuilder
  - [ ] 7.3 Verificar cobertura ≥ 70%

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

- [ ] 10. Relatório final
  - [ ] 10.1 Gerar coverage report final
  - [ ] 10.2 Criar gráfico de evolução
  - [ ] 10.3 Documentar modules restantes
  - [ ] 10.4 Commit e push
