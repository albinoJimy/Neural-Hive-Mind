# Optimizer Agents

## Visão Geral

**Optimizer Agents** é o componente responsável pela **melhoria contínua** do Neural Hive-Mind através de:

- **Reinforcement Learning + Contextual Bandits**: Aprendizado por reforço para otimizar políticas
- **Análise Causal**: Validação de relações causa-efeito antes de aplicar mudanças
- **Experimentos Controlados**: Validação de hipóteses através de testes A/B, canary, shadow
- **Recalibração Automática**: Ajuste de pesos de consenso e SLOs baseado em métricas

## Status da Implementação

**Versão**: 1.0.0 (Alpha - Estrutura Inicial)
**Progresso**: 35% completo

### ✅ Componentes Implementados

- Schemas Avro (optimization-event, experiment-request)
- Modelos Pydantic (OptimizationEvent, ExperimentRequest, OptimizationHypothesis)
- Configuração (settings.py, .env.example)
- Observabilidade (métricas Prometheus, tracing OpenTelemetry)
- API gRPC (proto definido, compilação pendente)
- API REST básica (health checks, metrics)
- Helm Chart completo
- Dockerfile multi-stage

### ⏳ Componentes Pendentes

- OptimizationEngine (Q-learning, epsilon-greedy)
- ExperimentManager (Argo Workflows integration)
- WeightRecalibrator (Consensus Engine integration)
- SLOAdjuster (Orchestrator integration)
- Kafka consumers/producers
- Clientes de integração (MongoDB, Redis, MLflow, gRPC)

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                     Optimizer Agents                        │
├─────────────────────────────────────────────────────────────┤
│  ┌────────────┐  ┌────────────┐  ┌──────────────────────┐  │
│  │ FastAPI    │  │ gRPC Server│  │ Kafka Consumers (3)  │  │
│  │ (REST API) │  │ (port 50051│  │ (insights, telemetry │  │
│  └─────┬──────┘  └─────┬──────┘  │  experiments)        │  │
│        │               │          └──────────┬───────────┘  │
│  ┌─────┴───────────────┴────────────────────┴───────────┐  │
│  │         Optimization Engine (RL + Bandits)            │  │
│  │  • Q-learning, Epsilon-greedy                         │  │
│  │  • Weight Recalibrator, SLO Adjuster                  │  │
│  │  • Experiment Manager (Argo Workflows)                │  │
│  └───────────────────────────────────────────────────────┘  │
│        │               │                    │               │
│  ┌─────┴──────┐  ┌────┴─────┐  ┌──────────┴───────────┐   │
│  │ MongoDB    │  │ Redis    │  │ MLflow + Argo        │   │
│  │ (ledger)   │  │(cache)   │  │ (experiments)        │   │
│  └────────────┘  └──────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Fluxo de Otimização

1. **Consumir insights** de Analyst Agents + telemetria de dashboards
2. **Identificar oportunidade** de otimização (análise causal)
3. **Gerar hipótese** de melhoria (RL/bandits)
4. **Submeter experimento** controlado (Argo Workflows)
5. **Analisar resultados** (DoWhy para causalidade)
6. **Aplicar otimização** validada (recalibração de pesos/SLOs)
7. **Publicar evento** `optimization.applied` no ledger
8. **Monitorar impacto** e rollback se necessário

## Configuração

### Variáveis de Ambiente

Copie `.env.example` para `.env` e ajuste:

```bash
# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka.kafka.svc.cluster.local:9092
KAFKA_INSIGHTS_TOPIC=insights.generated
KAFKA_TELEMETRY_TOPIC=telemetry.aggregated
KAFKA_OPTIMIZATION_TOPIC=optimization.applied
KAFKA_EXPERIMENTS_TOPIC=experiments.results

# gRPC Endpoints
CONSENSUS_ENGINE_ENDPOINT=consensus-engine:50051
ORCHESTRATOR_ENDPOINT=orchestrator-dynamic:50051
ANALYST_AGENTS_ENDPOINT=analyst-agents:50051
QUEEN_AGENT_ENDPOINT=queen-agent:50053

# MongoDB
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DATABASE=neural_hive
MONGODB_OPTIMIZATION_COLLECTION=optimization_ledger

# MLflow
MLFLOW_TRACKING_URI=http://mlflow:5000

# Argo Workflows
ARGO_SERVER_ENDPOINT=argo-server:2746

# Optimization Config
MIN_IMPROVEMENT_THRESHOLD=0.05
MAX_WEIGHT_ADJUSTMENT=0.2
LEARNING_RATE=0.01
EXPLORATION_RATE=0.1
DISCOUNT_FACTOR=0.95
REQUIRE_QUEEN_APPROVAL=true
```

## Build e Deploy

### Build Docker

```bash
make docker-build
make docker-push
```

### Deploy Kubernetes

```bash
# Lint Helm chart
make helm-lint

# Install
make helm-install

# Upgrade
make helm-upgrade
```

## Desenvolvimento

### Instalar dependências

```bash
make install
```

### Compilar Protocol Buffers

```bash
make proto
```

### Executar testes

```bash
make test
```

### Formatar código

```bash
make format
```

## Integrações

### Consensus Engine

Recalibração de pesos dos especialistas:

```python
# Ajustar pesos baseado em histórico de decisões
weights = weight_recalibrator.calculate_optimal_weights(historical_data)
consensus_client.update_weights(weights, justification, optimization_id)
```

### Orchestrator Dynamic

Ajuste de SLOs baseado em compliance:

```python
# Ajustar SLO se muito folgado ou apertado
slo_adjustment = slo_adjuster.propose_slo_adjustment(service, compliance_data)
orchestrator_client.update_slos(slo_adjustment, justification, optimization_id)
```

### Analyst Agents

Análise causal para validar hipóteses:

```python
# Validar causalidade antes de aplicar mudança
causal_evidence = causal_analyzer.analyze_optimization_causality(
    cause="weight_adjustment",
    effect="divergence_reduction",
    data=historical_data
)
```

### Queen Agent

Solicitar aprovação para otimizações de alto risco:

```python
# Otimizações com risk_score > 0.7 requerem aprovação
if optimization.risk_score > 0.7:
    approval = queen_client.request_approval(optimization_event)
```

## Métricas Prometheus

### Counters

- `optimizer_hypotheses_generated_total{optimization_type}`
- `optimizer_experiments_submitted_total{experiment_type}`
- `optimizer_optimizations_applied_total{optimization_type, component}`
- `optimizer_optimizations_rolled_back_total{optimization_type, component}`

### Gauges

- `optimizer_optimization_success_rate`
- `optimizer_average_improvement_percentage`
- `optimizer_experiments_active`
- `optimizer_q_table_size`
- `optimizer_epsilon_value`

### Histograms

- `optimizer_experiment_duration_seconds`
- `optimizer_optimization_processing_duration_seconds`
- `optimizer_weight_adjustment_magnitude`
- `optimizer_slo_adjustment_percentage`

## Schemas Avro

### OptimizationEvent

```json
{
  "optimization_id": "uuid",
  "optimization_type": "WEIGHT_RECALIBRATION | SLO_ADJUSTMENT | HEURISTIC_UPDATE | POLICY_CHANGE",
  "target_component": "consensus-engine",
  "experiment_id": "uuid",
  "hypothesis": "Ajustar peso do especialista técnico de 0.2 para 0.3 reduzirá divergência",
  "baseline_metrics": {"divergence": 0.15},
  "optimized_metrics": {"divergence": 0.08},
  "improvement_percentage": 0.47,
  "causal_analysis": {
    "method": "granger",
    "confidence": 0.85,
    "confounders": [],
    "effect_size": 0.47
  },
  "approval_status": "QUEEN_APPROVED"
}
```

### ExperimentRequest

```json
{
  "experiment_id": "uuid",
  "hypothesis": "Reduzir latência P95 em 20% através de cache Redis",
  "experiment_type": "A_B_TEST",
  "success_criteria": [
    {
      "metric_name": "latency_p95",
      "operator": "LT",
      "threshold": 800,
      "confidence_level": 0.95
    }
  ],
  "guardrails": [
    {
      "metric_name": "error_rate",
      "max_degradation_percentage": 0.05,
      "abort_threshold": 0.02
    }
  ],
  "traffic_percentage": 0.1,
  "duration_seconds": 3600
}
```

## Próximos Passos

### Prioridade Alta

1. Implementar OptimizationEngine (RL + Bandits)
2. Implementar ExperimentManager (Argo Workflows)
3. Implementar clientes gRPC (Consensus, Orchestrator, Analyst, Queen)
4. Implementar Kafka consumers/producers
5. Estender protos existentes (consensus_engine, orchestrator)

### Prioridade Média

6. Implementar WeightRecalibrator e SLOAdjuster
7. Implementar clientes de database (MongoDB, Redis)
8. Implementar APIs REST completas
9. Implementar gRPC server

### Prioridade Baixa

10. Dashboard Grafana
11. Alertas Prometheus
12. Testes unitários e E2E
13. Documentação completa

## Licença

Neural Hive-Mind © 2025
