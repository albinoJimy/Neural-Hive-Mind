# Tasks - Test Coverage Improvement

## Epic A: Gateway e NLU (+100 testes)

- [ ] A001 - Testes para gateway-intencoes (+50 testes)
  - [ ] A001.1 Testar NLU Pipeline (intent classification, entity extraction)
  - [ ] A001.2 Testar ASR Pipeline (audio processing)
  - [ ] A001.3 Testar Router (roteamento adaptativo)
  - [ ] A001.4 Testar PIIDetector (masking)
  - [ ] A001.5 Testar rate limiting
  - [ ] A001.6 Testar authentication middleware
  - [ ] A001.7 Testar error handling

- [ ] A002 - Testes para semantic-translation-engine (+50 testes)
  - [ ] A002.1 Testar Semantic Parser
  - [ ] A002.2 Testar DAG Generator
  - [ ] A002.3 Testar Intent Decomposer
  - [ ] A002.4 Testar Context Enricher
  - [ ] A002.5 Testar Neo4j integration
  - [ ] A002.6 Testar DLQ (dead letter queue)

## Epic B: Orquestração e Agents (+100 testes)

- [ ] B001 - Testes para orchestrator-dynamic (+30 testes)
  - [ ] B001.1 Testar Temporal workflow creation
  - [ ] B001.2 Testar InsightsConsumer
  - [ ] B001.3 Testar StrategicDecisionConsumer
  - [ ] B001.4 Testar workflow state management
  - [ ] B001.5 Testar saga compensation
  - [ ] B001.6 Testar SLA monitoring

- [ ] B002 - Testes para queen-agent (+40 testes)
  - [ ] B002.1 Testar agent discovery
  - [ ] B002.2 Testar agent orchestration
  - [ ] B002.3 Testar health checks
  - [ ] B002.4 Testar metrics collection
  - [ ] B002.5 Testar leader election

- [ ] B003 - Testes para worker-agents (+30 testes)
  - [ ] B003.1 Testar QueryExecutor
  - [ ] B003.2 Testar TransformExecutor
  - [ ] B003.3 Testar ValidateExecutor
  - [ ] B003.4 Testar ExecutionEngine
  - [ ] B003.5 Testar result aggregation

## Epic C: Specialists (+120 testes)

- [ ] C001 - Testes para specialist-business (+20 testes)
  - [ ] C001.1 Testar análise de negócio
  - [ ] C001.2 Testar features extraction
  - [ ] C001.3 Testar ML integration

- [ ] C002 - Testes para specialist-technical (+20 testes)
  - [ ] C002.1 Testar análise técnica
  - [ ] C002.2 Testar code quality metrics

- [ ] C003 - Testes para specialist-architecture (+20 testes)
  - [ ] C003.1 Testar SOLID compliance
  - [ ] C003.2 Testar design patterns

- [ ] C004 - Testes para specialist-behavior (+20 testes)
  - [ ] C004.1 Testar UX analysis
  - [ ] C004.2 Testar usability metrics

- [ ] C005 - Testes para specialist-evolution (+20 testes)
  - [ ] C005.1 Testar scalability analysis
  - [ ] C005.2 Testar tech debt detection

- [ ] C006 - Testes para approval-service (+20 testes adicionais)
  - [ ] C006.1 Testar ML predictor
  - [ ] C006.2 Testar active learning
  - [ ] C006.3 Testar feedback collection

## Epic D: Bibliotecas Core (+150 testes)

- [ ] D001 - Testes para neural_hive_domain (+50 testes)
  - [ ] D001.1 Testar CognitivePlan models
  - [ ] D001.2 Testar SpecialistOpinion models
  - [ ] D001.3 Testar DTOs
  - [ ] D001.4 Testar Events
  - [ ] D001.5 Testar Value Objects

- [ ] D002 - Testes para neural_hive_agent_sdk (+30 testes)
  - [ ] D002.1 Testar AgentClient
  - [ ] D002.2 Testar gRPC communication
  - [ ] D002.3 Testar retry logic
  - [ ] D002.4 Testar circuit breaker

- [ ] D003 - Testes para neural_hive_ml (+40 testes)
  - [ ] D003.1 Testar SchedulingPredictor
  - [ ] D003.2 Testar AnomalyDetector
  - [ ] D003.3 Testar DriftDetector
  - [ ] D003.4 Testar MLflowClient
  - [ ] D003.5 Testar RetrainingJob

- [ ] D004 - Testes para neural_hive_risk_scoring (+30 testes)
  - [ ] D004.1 Testar RiskCalculator
  - [ ] D004.2 Testar RiskScoringEngine
  - [ ] D004.3 Testar DynamicThresholds
  - [ ] D004.4 Testar RiskHistory
  - [ ] D004.5 Testar AlertManager

## Epic E: Outros Serviços (+70 testes)

- [ ] E001 - Testes para guard-agents (+20 testes)
  - [ ] E001.1 Testar SignalDetector
  - [ ] E001.2 Testar ExplorationEngine
  - [ ] E001.3 Testar incident feedback

- [ ] E002 - Testes para scout-agents (+20 testes)
  - [ ] E002.1 Testar signal processing
  - [ ] E002.2 Testar pattern detection

- [ ] E003 - Testes para optimizer-agents (+30 testes)
  - [ ] E003.1 Testar AutoApplier
  - [ ] E003.2 Testar ExperimentManager
  - [ ] E003.3 Testar InsightsConsumer

## Epic F: Infraestrutura de Testes (+60 testes)

- [ ] F001 - Configurar pytest-cov
  - [ ] F001.1 Actualizar pytest.ini com cov config
  - [ ] F001.2 ConfigurarCoverage.fail_under = 60
  - [ ] F001.3 Adicionar relatório HTML

- [ ] F002 - Criar fixtures comuns
  - [ ] F002.1 Criar conftest.py global
  - [ ] F002.2 Criar mock_config fixture
  - [ ] F002.3 Criar mock_mongodb fixture
  - [ ] F002.4 Criar mock_kafka fixture
  - [ ] F002.5 Criar mock_redis fixture

- [ ] F003 - Integrar com CI/CD
  - [ ] F003.1 Adicionar step de coverage no workflow
  - [ ] F003.2 Configurar Codecov ou similar
  - [ ] F003.3 Adicionar badge no README

- [ ] F004 - Criar test helpers
  - [ ] F004.1 Criar factories para test data
  - [ ] F004.2 Criar assert helpers
  - [ ] F004.3 Criar integration test helpers

## Epic G: Validação Final

- [ ] G001 - Validar cobertura 60%
  - [ ] G001.1 Executar `pytest --cov --cov-report=term`
  - [ ] G001.2 Verificar que cobertura >= 60%
  - [ ] G001.3 Gerar relatório HTML

- [ ] G002 - Commit e PR
  - [ ] G002.1 Fazer git add dos testes criados
  - [ ] G002.2 Criar commit descritivo
  - [ ] G002.3 Push e criar PR

## Resumo

| Epic | Testes | Estimativa |
|------|--------|------------|
| A: Gateway e NLU | +100 | 8-10h |
| B: Orquestração | +100 | 6-8h |
| C: Specialists | +120 | 8-10h |
| D: Bibliotecas | +150 | 10-12h |
| E: Outros | +70 | 4-6h |
| F: Infraestrutura | +60 | 4-6h |
| **TOTAL** | **+600** | **40-52h** |

**Nota:** Esta é uma spec de longo prazo. Recomenda-se executar por epics separados.
