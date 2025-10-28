# Optimizer Agents - Guia de Implementação

## Visão Geral

Os **Optimizer Agents** implementam um sistema de melhoria contínua autônoma usando **Reinforcement Learning (Q-learning)** e **Contextual Bandits** para otimizar dinamicamente o Neural Hive-Mind através de:

1. **Recalibração de Pesos** de especialistas no Consensus Engine
2. **Ajuste de SLOs** no Orchestrator Dynamic
3. **Otimização de Heurísticas** e políticas do sistema
4. **Gestão de Experimentos** controlados via Argo Workflows

## Arquitetura

```
┌──────────────────────────────────────────────────────────────────┐
│                      Optimizer Agents                            │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   Camada de APIs                          │   │
│  │  • REST API (FastAPI): 14 endpoints                       │   │
│  │  • gRPC Server: 6 métodos RPC                             │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Camada de Integração Kafka                   │   │
│  │  Consumers:                     Producers:                │   │
│  │  • InsightsConsumer            • OptimizationProducer     │   │
│  │  • TelemetryConsumer           • ExperimentProducer       │   │
│  │  • ExperimentsConsumer                                    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  Camada de Serviços Core                  │   │
│  │  • OptimizationEngine (RL Q-learning, epsilon-greedy)     │   │
│  │  • ExperimentManager (Argo Workflows integration)         │   │
│  │  • WeightRecalibrator (Consensus Engine optimization)     │   │
│  │  • SLOAdjuster (Orchestrator optimization)                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  Camada de Clientes                       │   │
│  │  DB/Cache:             ML/Workflows:      gRPC:           │   │
│  │  • MongoDB             • MLflow           • ConsensusEngine│
│  │  • Redis               • Argo Workflows  • Orchestrator   │   │
│  │                                           • AnalystAgents  │   │
│  │                                           • QueenAgent     │   │
│  │                                           • ServiceRegistry│   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

## Componentes Principais

### 1. OptimizationEngine

**Propósito**: Motor de Reinforcement Learning que aprende quais otimizações aplicar em cada situação.

**Algoritmo**: Q-learning com epsilon-greedy
- **Q-table**: Mapeia estados → ações → valores Q
- **Epsilon-greedy**: Balanceia exploração vs exploração (ε decay de 0.3 → 0.01)
- **Reward function**: `improvement - (risk * penalty_factor)`
- **Update rule**: `Q(s,a) = Q(s,a) + α * [r + γ * max(Q(s',a')) - Q(s,a)]`

**Parâmetros**:
```python
learning_rate (α) = 0.01
exploration_rate (ε) = 0.1 (com decay)
discount_factor (γ) = 0.95
min_improvement_threshold = 0.05 (5%)
```

**Tipos de Otimização**:
1. `WEIGHT_RECALIBRATION`: Ajusta pesos de especialistas
2. `SLO_ADJUSTMENT`: Ajusta SLOs de serviços
3. `HEURISTIC_UPDATE`: Atualiza heurísticas de decisão
4. `POLICY_CHANGE`: Muda políticas de sistema

**Fluxo de Geração de Hipótese**:
```
1. Recebe insight (degradação ou oportunidade)
2. Extrai estado atual do sistema
3. Seleciona ação via epsilon-greedy
4. Gera hipótese com Q-value, confidence, risk
5. Retorna hipótese para validação
```

### 2. ExperimentManager

**Propósito**: Gerencia experimentos controlados para validar hipóteses antes de aplicar.

**Tipos de Experimento**:
- **A/B Test**: Comparação baseline vs experimental
- **Canary**: Rollout gradual (ex: 10% → 50% → 100%)
- **Shadow**: Traffic mirroring sem impacto
- **Multi-Armed Bandit**: Seleção adaptativa de variantes

**Pipeline de Experimento** (via Argo Workflows):
```
1. Setup Baseline        → Deploy configuração atual
2. Setup Experimental    → Deploy configuração experimental
3. Traffic Split         → Divide tráfego (ex: 90%/10%)
4. Monitor              → Monitora guardrails (30min-2h)
5. Collect Metrics      → Coleta métricas de Prometheus
6. Analyze Results      → Valida success criteria
7. Cleanup              → Remove recursos temporários
```

**Guardrails**:
- Abort automático se violação (ex: error_rate > 5%)
- Timeout máximo configurável
- Rollback automático em caso de falha

### 3. WeightRecalibrator

**Propósito**: Aplica recalibrações de peso no Consensus Engine.

**Validações**:
```python
# 1. Pesos somam 1.0 (±0.01 tolerância)
total_weight = sum(weights.values())
assert 0.99 <= total_weight <= 1.01

# 2. Pesos individuais entre 0.1 e 0.4 (evitar dominância)
for weight in weights.values():
    assert 0.1 <= weight <= 0.4

# 3. Todos especialistas presentes
required = {"technical", "safety", "business", "ethical", "legal"}
assert set(weights.keys()) == required
```

**Aplicação**:
1. Adquire distributed lock via Redis
2. Obtém pesos atuais do Consensus Engine
3. Calcula pesos propostos (delta limitado)
4. Normaliza para somar 1.0
5. Valida via `validate_weight_adjustment()`
6. Aplica via `update_weights()`
7. Publica `OptimizationEvent` no Kafka
8. Libera lock

### 4. SLOAdjuster

**Propósito**: Ajusta SLOs do Orchestrator Dynamic.

**Limites de Segurança**:
```python
# Latência: ±30% máximo
current_latency = 1000ms
max_change = current_latency * 0.3  # ±300ms
new_latency = clamp(proposed, 700ms, 1300ms)

# Availability: 0.95 - 0.9999
new_availability = clamp(proposed, 0.95, 0.9999)

# Error Rate: 0.001 - 0.10
new_error_rate = clamp(proposed, 0.001, 0.10)
```

**Verificações**:
1. Error budget >= 20% (não ajustar se budget baixo)
2. Validação via `validate_slo_adjustment()`
3. Distributed lock via Redis
4. Aplicação via `update_slos()`
5. Monitoramento de impacto (24h)

## Integração Kafka

### Consumers

**InsightsConsumer** (`insights.generated`):
- Filtra insights HIGH/CRITICAL do Analyst Agents
- Passa para `OptimizationEngine.analyze_opportunity()`
- Gera hipóteses de otimização

**TelemetryConsumer** (`telemetry.aggregated`):
- Detecta degradações: SLO < 99%, latency > 1000ms, error_rate > 1%
- Cria insights sintéticos
- Aciona geração de hipóteses

**ExperimentsConsumer** (`experiments.results`):
- Processa resultados de experimentos
- Calcula reward (+/- baseado em sucesso)
- Atualiza Q-table via `update_q_table()`

### Producers

**OptimizationProducer** (`optimization.applied`):
- Publica eventos de otimização aplicados
- Schema Avro: OptimizationEvent
- Inclui causal_analysis, adjustments, rollback_plan, hash SHA-256

**ExperimentProducer** (`experiments.requests`):
- Publica requisições de experimentos
- Schema Avro: ExperimentRequest
- Inclui hypothesis, success_criteria, guardrails

## APIs

### REST API (FastAPI)

**Optimizations** (`/api/v1/optimizations`):
```
POST   /trigger                 - Trigger manual de otimização
GET    /                        - Listar otimizações (filtros: tipo, componente, status)
GET    /{id}                    - Obter detalhes de otimização
POST   /{id}/rollback           - Reverter otimização
GET    /statistics/summary      - Estatísticas agregadas
```

**Experiments** (`/api/v1/experiments`):
```
POST   /submit                  - Submeter experimento
GET    /                        - Listar experimentos (filtros: tipo, status)
GET    /{id}                    - Obter detalhes
POST   /{id}/abort              - Abortar experimento em execução
GET    /{id}/results            - Obter análise de resultados
GET    /statistics/summary      - Estatísticas agregadas
```

### gRPC Server

**OptimizerAgent** service:
```protobuf
rpc TriggerOptimization(TriggerOptimizationRequest) returns (TriggerOptimizationResponse);
rpc GetOptimizationStatus(GetOptimizationStatusRequest) returns (GetOptimizationStatusResponse);
rpc ListOptimizations(ListOptimizationsRequest) returns (stream OptimizationInfo);
rpc RollbackOptimization(RollbackOptimizationRequest) returns (RollbackOptimizationResponse);
rpc GetStatistics(GetStatisticsRequest) returns (GetStatisticsResponse);
rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
```

## Observabilidade

### Métricas Prometheus (20+)

**Counters**:
- `hypotheses_generated_total{type}` - Hipóteses geradas por tipo
- `experiments_submitted_total{type}` - Experimentos submetidos
- `experiments_succeeded_total` - Experimentos bem-sucedidos
- `experiments_failed_total` - Experimentos falhados
- `optimizations_applied_total{type}` - Otimizações aplicadas
- `rollbacks_total{type}` - Rollbacks executados
- `q_table_updates_total` - Atualizações da Q-table

**Gauges**:
- `experiments_active` - Experimentos em execução
- `optimization_success_rate` - Taxa de sucesso
- `average_improvement_percentage` - Melhoria média
- `q_table_size` - Número de estados na Q-table
- `epsilon_value` - Taxa de exploração atual

**Histograms**:
- `experiment_duration_seconds` - Duração de experimentos
- `optimization_processing_duration_seconds` - Tempo de processamento
- `weight_adjustment_magnitude` - Magnitude de ajustes de peso
- `reward_distribution` - Distribuição de rewards

### Dashboard Grafana

**15 painéis em 6 seções**:
1. **Overview**: Total optimizations, success rate, avg improvement, active experiments
2. **RL**: Q-table size, epsilon decay, hypotheses by type, reward heatmap
3. **Experiments**: Submission rate, duration P95/P50, success pie chart
4. **Optimizations**: By type (stacked), weight magnitude, rollbacks
5. **Performance**: Processing duration, Kafka lag
6. **Resources**: CPU/memory per pod

### Alertas Prometheus (19 alertas)

**Critical**:
- `OptimizerAgentsDown`: Service down > 2min
- `HighOptimizationFailureRate`: Failure rate > 30%
- `ExperimentStuckInProgress`: Active but no new submissions > 30min
- `QLearningNotUpdating`: Q-table not updating > 15min

**Warning**:
- `LowOptimizationSuccessRate`: Success rate < 80%
- `HighExperimentFailureRate`: Experiment failures > 20%
- `ExcessiveRollbacks`: Rollback rate > 0.1/s
- `LowImprovementRate`: Avg improvement < 3%
- `HighEpsilonValue`: Epsilon > 30% after 24h
- `KafkaConsumerLagHigh`: Lag > 1000 messages

## Deployment

### Helm Chart

**values.yaml**:
```yaml
replicaCount: 2

image:
  repository: optimizer-agents
  tag: latest
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  ports:
    grpc: 50051
    http: 8000
    metrics: 9090

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70

resources:
  requests:
    cpu: 500m
    memory: 1Gi
  limits:
    cpu: 1000m
    memory: 2Gi

env:
  KAFKA_BOOTSTRAP_SERVERS: "kafka:9092"
  MONGODB_URI: "mongodb://mongodb:27017"
  REDIS_HOST: "redis"
  MLFLOW_TRACKING_URI: "http://mlflow:5000"
  ARGO_SERVER_ENDPOINT: "argo-server:2746"
```

**Deploy**:
```bash
helm install optimizer-agents ./helm-chart \
  --namespace neural-hive-mind \
  --create-namespace \
  --values values.yaml
```

### Configuração de Ambiente

**Variáveis principais** (.env):
```bash
# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_INSIGHTS_TOPIC=insights.generated
KAFKA_TELEMETRY_TOPIC=telemetry.aggregated
KAFKA_EXPERIMENTS_TOPIC=experiments.results
KAFKA_OPTIMIZATION_TOPIC=optimization.applied

# gRPC Endpoints
CONSENSUS_ENGINE_ENDPOINT=consensus-engine:50051
ORCHESTRATOR_ENDPOINT=orchestrator:50051
ANALYST_AGENTS_ENDPOINT=analyst-agents:50051
QUEEN_AGENT_ENDPOINT=queen-agent:50051
SERVICE_REGISTRY_ENDPOINT=service-registry:50051

# Databases
MONGODB_URI=mongodb://mongodb:27017/optimizer_agents
REDIS_HOST=redis
REDIS_PORT=6379

# ML/Workflows
MLFLOW_TRACKING_URI=http://mlflow:5000
MLFLOW_EXPERIMENT_NAME=optimizer-agents
ARGO_SERVER_ENDPOINT=argo-server:2746
ARGO_WORKFLOWS_NAMESPACE=argo

# Optimization Config
LEARNING_RATE=0.01
EXPLORATION_RATE=0.1
DISCOUNT_FACTOR=0.95
MIN_IMPROVEMENT_THRESHOLD=0.05
MAX_WEIGHT_ADJUSTMENT=0.2
```

## Desenvolvimento

### Setup Local

```bash
# 1. Instalar dependências
cd services/optimizer-agents
pip install -r requirements.txt

# 2. Configurar ambiente
cp .env.example .env
# Editar .env com configurações locais

# 3. Compilar protos (quando disponível)
make proto

# 4. Executar testes
pytest tests/

# 5. Executar serviço
python -m src.main
```

### Estrutura de Diretórios

```
services/optimizer-agents/
├── src/
│   ├── api/                  # REST endpoints
│   ├── clients/              # DB, ML, gRPC clients
│   ├── config/               # Settings
│   ├── consumers/            # Kafka consumers
│   ├── grpc_service/         # gRPC server
│   ├── models/               # Pydantic models
│   ├── observability/        # Metrics, tracing
│   ├── producers/            # Kafka producers
│   ├── proto/                # Protocol Buffers
│   ├── services/             # Core logic
│   └── main.py               # Entry point
├── helm-chart/               # Kubernetes deployment
├── tests/                    # Unit/integration tests
├── Dockerfile
├── requirements.txt
└── README.md
```

## Troubleshooting

### Q-table não está atualizando

**Sintomas**: Métrica `q_table_updates_total` zerada

**Diagnóstico**:
```bash
# Verificar se experimentos estão completando
kubectl logs -n neural-hive-mind optimizer-agents-xxx | grep "q_table_updated"

# Verificar consumer de experimentos
kubectl logs -n neural-hive-mind optimizer-agents-xxx | grep "ExperimentsConsumer"
```

**Solução**: Verificar se tópico `experiments.results` está sendo publicado

### Alta taxa de rollbacks

**Sintomas**: Alerta `ExcessiveRollbacks` ativo

**Diagnóstico**:
```bash
# Ver rollbacks recentes
curl http://optimizer-agents:8000/api/v1/optimizations?status=ROLLED_BACK

# Analisar logs
kubectl logs -n neural-hive-mind optimizer-agents-xxx | grep "rollback"
```

**Solução**: Ajustar thresholds de sucesso ou guardrails de experimentos

### Experimentos demorando muito

**Sintomas**: P95 > 2h

**Diagnóstico**:
```bash
# Ver experimentos ativos
kubectl get workflows -n argo | grep optimizer

# Verificar logs do workflow
argo logs -n argo <workflow-name>
```

**Solução**: Reduzir `duration_seconds` ou otimizar pipeline

## Segurança

### Validações Implementadas

1. **Weight Adjustments**: Validação de limites (0.1-0.4, soma = 1.0)
2. **SLO Adjustments**: Limites de segurança (latency ±30%, availability 0.95-0.9999)
3. **Distributed Locks**: Previne otimizações concorrentes
4. **Error Budget**: Não ajusta SLOs se budget < 20%
5. **Approval Flow**: Alto risco (>0.5) requer aprovação Queen Agent

### Rollback Strategy

**Automático**:
- Violação de guardrails durante experimento
- Falha de aplicação de otimização
- Degradação detectada pós-aplicação

**Manual**:
```bash
# Via REST API
curl -X POST http://optimizer-agents:8000/api/v1/optimizations/{id}/rollback

# Via gRPC
grpcurl -d '{"optimization_id": "opt-123"}' \
  optimizer-agents:50051 \
  OptimizerAgent/RollbackOptimization
```

## Referências

- **Q-learning**: Sutton & Barto, "Reinforcement Learning: An Introduction"
- **Argo Workflows**: https://argoproj.github.io/argo-workflows/
- **MLflow**: https://mlflow.org/docs/latest/
- **Prometheus**: https://prometheus.io/docs/
- **Grafana**: https://grafana.com/docs/

## Contato

Para questões ou suporte:
- Documentação: `/docs` (FastAPI auto-docs)
- Métricas: `http://optimizer-agents:9090/metrics`
- Health: `http://optimizer-agents:8000/health`
