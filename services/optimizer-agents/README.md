# Optimizer Agents

## Visão Geral

**Optimizer Agents** é o componente responsável pela **melhoria contínua** do Neural Hive-Mind através de:

- **Reinforcement Learning + Contextual Bandits**: Aprendizado por reforço para otimizar políticas
- **Análise Causal**: Validação de relações causa-efeito antes de aplicar mudanças
- **Experimentos Controlados**: Validação de hipóteses através de testes A/B, canary, shadow
- **Recalibração Automática**: Ajuste de pesos de consenso e SLOs baseado em métricas

## Status da Implementação

**Versão**: 1.0.0 (Production Ready)
**Progresso**: 100% completo

### ✅ Componentes Implementados (100%)

- ✅ **Schemas Avro** (optimization-event, experiment-request)
- ✅ **Modelos Pydantic** completos (OptimizationEvent, ExperimentRequest, OptimizationHypothesis)
- ✅ **OptimizationEngine** (Q-learning, epsilon-greedy) - 438 linhas completas
- ✅ **ExperimentManager** (Argo Workflows integration) - 555 linhas completas
- ✅ **WeightRecalibrator** - 267 linhas completas
- ✅ **SLOAdjuster** - 287 linhas completas
- ✅ **Kafka consumers** (3) e **producers** (2) - completos
- ✅ **Clientes gRPC** (4) - com proto compilado e fallback stubs
- ✅ **API gRPC** (11 métodos) - OptimizerServicer completo com proto messages
- ✅ **API REST** (health, metrics) - completa
- ✅ **ML Subsystem** - LoadPredictor, SchedulingOptimizer, ModelRegistry, TrainingPipeline
- ✅ **Observabilidade** (métricas Prometheus, tracing OpenTelemetry) - completa
- ✅ **Helm Chart** completo
- ✅ **Dockerfile** multi-stage
- ✅ **Testes** de validação
- ✅ **Script de validação** de deployment

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

## gRPC Integration

### Compilar Protos
```bash
make proto
```

### Clientes gRPC Disponíveis
- `AnalystAgentsGrpcClient`: Comunicação com Analyst Agents
- `QueenAgentGrpcClient`: Comunicação com Queen Agent

### Exemplo de Uso
Ver `docs/grpc-integration-guide.md` para exemplos completos.

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

### Validação de Deployment

Após deploy, validar com:

```bash
./scripts/validate-deployment.sh
```

Verificar logs:

```bash
kubectl logs -n neural-hive-orchestration -l app=optimizer-agents --tail=100 -f
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

## Dependency Injection Pattern

### Visão Geral

O Optimizer Agents utiliza o padrão de **Dependency Injection** do FastAPI para desacoplar as APIs REST dos serviços internos. Isso permite:

- **Testabilidade**: Substituir dependências reais por mocks em testes
- **Flexibilidade**: Trocar implementações sem modificar código das APIs
- **Manutenibilidade**: Centralizar inicialização de serviços no `main.py`

### Arquitetura de DI

```
┌─────────────────────────────────────────────────────────┐
│                    main.py (startup)                    │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 1. Inicializar serviços globais                  │  │
│  │    - mongodb_client, redis_client                │  │
│  │    - optimization_engine, experiment_manager     │  │
│  │    - weight_recalibrator, slo_adjuster           │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 2. Configurar app.dependency_overrides           │  │
│  │    - optimizations.get_mongodb_client            │  │
│  │    - optimizations.get_optimization_engine       │  │
│  │    - experiments.get_experiment_manager          │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │
                          ↓
┌─────────────────────────────────────────────────────────┐
│              API Routers (optimizations.py)             │
│  ┌──────────────────────────────────────────────────┐  │
│  │ def get_mongodb_client() -> MongoDBClient:       │  │
│  │     raise NotImplementedError  # Placeholder     │  │
│  │                                                   │  │
│  │ @router.get("")                                  │  │
│  │ async def list_optimizations(                    │  │
│  │     mongodb: MongoDBClient = Depends(get_...)    │  │
│  │ ):                                               │  │
│  │     # Usa instância injetada via override        │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Dependências Configuradas

#### API de Otimizações (`src/api/optimizations.py`)

| Função de Dependency | Serviço Injetado | Uso |
|---------------------|------------------|-----|
| `get_mongodb_client()` | `MongoDBClient` | Persistência de otimizações |
| `get_redis_client()` | `RedisClient` | Cache de estado |
| `get_optimization_engine()` | `OptimizationEngine` | Geração de hipóteses |
| `get_weight_recalibrator()` | `WeightRecalibrator` | Recalibração de pesos |
| `get_slo_adjuster()` | `SLOAdjuster` | Ajuste de SLOs |

#### API de Experimentos (`src/api/experiments.py`)

| Função de Dependency | Serviço Injetado | Uso |
|---------------------|------------------|-----|
| `get_mongodb_client()` | `MongoDBClient` | Persistência de experimentos |
| `get_experiment_manager()` | `ExperimentManager` | Gestão de experimentos |

### Exemplo de Uso em Testes

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

def test_list_optimizations_with_mock():
    from src.api import optimizations

    # Criar app de teste
    app = FastAPI()
    app.include_router(optimizations.router)

    # Criar mock do MongoDB
    mock_mongodb = MagicMock()
    mock_mongodb.list_optimizations = AsyncMock(return_value=[
        {'optimization_id': 'opt-123', 'status': 'APPROVED'}
    ])

    # Configurar override
    app.dependency_overrides[optimizations.get_mongodb_client] = lambda: mock_mongodb

    # Testar endpoint
    client = TestClient(app)
    response = client.get('/api/v1/optimizations')

    assert response.status_code == 200
    assert len(response.json()['optimizations']) == 1
```

### Configuração em Produção

Em produção, os overrides são configurados automaticamente no `startup()` do `main.py`:

```python
# services/optimizer-agents/src/main.py (linhas 486-518)
async def startup():
    # ... inicializar serviços ...

    # Configurar dependency overrides
    app.dependency_overrides[optimizations.get_mongodb_client] = override_mongodb_client
    app.dependency_overrides[optimizations.get_redis_client] = override_redis_client
    # ... outros overrides ...
```

**Importante**: As funções `get_*()` nas APIs **sempre** lançam `NotImplementedError` por padrão. Elas são substituídas pelos overrides no startup.

### Troubleshooting

#### Erro: "NotImplementedError: MongoDBClient dependency not configured"

**Causa**: Endpoint foi chamado antes do `startup()` completar ou overrides não foram configurados.

**Solução**:
1. Verificar que o serviço iniciou completamente (logs: `"optimizer_agents_started"`)
2. Verificar que `app.dependency_overrides` está populado no `main.py`
3. Em testes, sempre configurar overrides manualmente

#### Erro: "AttributeError: 'NoneType' object has no attribute 'list_optimizations'"

**Causa**: Serviço global (`mongodb_client`) é `None` quando override é chamado.

**Solução**:
1. Verificar ordem de inicialização no `startup()` (serviços antes de overrides)
2. Verificar que conexões foram estabelecidas com sucesso
3. Checar logs de erro durante inicialização

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

## Melhorias Futuras

### Curto Prazo

1. Adicionar mais tipos de otimização (HEURISTIC_UPDATE, POLICY_CHANGE)
2. Implementar análise causal avançada com DoWhy
3. Adicionar suporte para multi-objective optimization
4. Expandir cobertura de testes unitários e E2E

### Médio Prazo

5. Implementar meta-learning para transfer learning entre componentes
6. Adicionar suporte para federated learning
7. Implementar AutoML para hyperparameter tuning
8. Dashboard Grafana customizado para métricas de otimização
11. Alertas Prometheus
12. Testes unitários e E2E
13. Documentação completa

## Licença

Neural Hive-Mind © 2025
