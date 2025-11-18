# ML Scheduling Optimization - Orchestrator Dynamic

## Visão Geral

O **ML Scheduling Optimization** é um sistema de otimização inteligente de scheduling que combina predições de Machine Learning remotas (via Optimizer Agents) com fallbacks heurísticos locais para melhorar a qualidade de alocação de workers.

### Arquitetura Dual-Mode

O sistema opera em modo dual com dois níveis de otimização:

1. **Remote Optimizer (Prophet/ARIMA + Q-learning RL)**: Predições sofisticadas de carga futura e recomendações de RL policy do serviço `optimizer-agents`.
2. **Local Fallback (Heurísticas Leves)**: Predições baseadas em dados históricos do MongoDB com latência <50ms.

```
┌─────────────────────────────────────────────────────────────────┐
│                    IntelligentScheduler                         │
│  (Orquestra alocação de workers para execution tickets)         │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               v
┌─────────────────────────────────────────────────────────────────┐
│                    SchedulingOptimizer                          │
│  (Facade para otimização ML - coordena remote + local)          │
└───────┬─────────────────────────────────┬───────────────────────┘
        │                                 │
        v                                 v
┌──────────────────┐            ┌──────────────────────┐
│ OptimizerGrpcClient          │  LoadPredictor        │
│ (Remote)                     │  (Local Fallback)     │
│                              │                       │
│ - Prophet/ARIMA              │ - Moving averages     │
│ - Q-learning RL              │ - Exponential smoothing
│ - Load forecasts             │ - Redis cache (<50ms) │
└──────────────────┘            └──────────────────────┘
        │                                 │
        └────────────┬────────────────────┘
                     v
          ┌──────────────────────┐
          │  ResourceAllocator   │
          │  (Worker Selection)  │
          │                      │
          │ - Aplica rl_boost    │
          │ - Score composto     │
          └──────────────────────┘
```

## Componentes

### 1. SchedulingOptimizer

**Localização**: `src/ml/scheduling_optimizer.py`

**Responsabilidades**:
- Obter **load forecasts** do optimizer-agents (carga futura do sistema)
- Enriquecer workers com **predições de queue time** e **worker load** (via LoadPredictor local)
- Solicitar **recomendações de RL policy** (SCALE_UP, CONSOLIDATE, MAINTAIN)
- Aplicar **rl_boost** aos workers conforme ação RL
- Publicar **allocation outcomes** no Kafka para feedback loop de RL training

**Principais Métodos**:
```python
async def get_load_forecast(horizon_minutes: int = 60) -> Optional[Dict]
async def optimize_allocation(ticket: Dict, workers: List[Dict], load_forecast: Optional[Dict]) -> List[Dict]
async def record_allocation_outcome(ticket: Dict, worker: Dict, actual_duration_ms: float)
```

---

### 2. LoadPredictor

**Localização**: `src/ml/load_predictor.py`

**Responsabilidades**:
- Predizer **queue time** (tempo de espera em fila) para cada worker
- Predizer **worker load** (percentual de carga atual) baseado em queue depth
- Cache de predições em Redis (TTL configurável)
- Fallback seguro quando MongoDB indisponível

**Principais Métodos**:
```python
async def predict_queue_time(worker_id: str, ticket: Optional[Dict]) -> float  # retorna ms
async def predict_worker_load(worker_id: str) -> float  # retorna 0.0-1.0
```

**Algoritmos**:
- **Queue Time**: `queue_depth * moving_average(recent_durations)` com exponential smoothing
- **Worker Load**: `queue_depth / max_capacity` (capacidade default: 10 tarefas)

---

### 3. ResourceAllocator

**Localização**: `src/scheduler/resource_allocator.py`

**Responsabilidades**:
- Descobrir workers via Service Registry
- Calcular **agent_score** composto (health + telemetry + ML predictions)
- Aplicar **rl_boost** multiplicador ao score (quando RL recommendation aplicado)
- Selecionar melhor worker para cada ticket

**Cálculo de Score**:

**Sem ML**:
```
agent_score = (health_score * 0.5) + (telemetry_score * 0.5)
```

**Com ML**:
```
agent_score = (health_score * 0.4) + (telemetry_score * 0.3) + (queue_score * 0.2) + (load_score * 0.1)
```

**Com RL Boost**:
```
final_score = agent_score * rl_boost  # rl_boost: 1.0 (sem boost), 1.1-1.2 (boost moderado)
```

---

## Configuração

### Variáveis de Ambiente

#### Remote Optimizer Integration

```yaml
# Habilitar integração com optimizer-agents remoto (Prophet/ARIMA + RL)
ENABLE_OPTIMIZER_INTEGRATION=false  # Habilitar após validação em staging
OPTIMIZER_AGENTS_ENDPOINT=optimizer-agents.neural-hive-estrategica.svc.cluster.local:50051
OPTIMIZER_GRPC_TIMEOUT=10  # segundos
OPTIMIZER_FORECAST_HORIZON_MINUTES=60  # Horizonte de previsão de carga
```

#### Local Load Prediction (Fallback)

```yaml
# Heurísticas locais (sempre habilitado para fallback)
ML_LOCAL_LOAD_PREDICTION_ENABLED=true
ML_LOCAL_LOAD_CACHE_TTL_SECONDS=30  # TTL do cache Redis
ML_LOCAL_LOAD_WINDOW_MINUTES=60  # Janela de dados históricos
ML_QUEUE_PREDICTION_WEIGHT=0.2  # Peso de queue time no score composto
ML_LOAD_PREDICTION_WEIGHT=0.1  # Peso de carga no score composto
ML_OPTIMIZATION_TIMEOUT_SECONDS=2  # Timeout para otimização ML
```

#### Allocation Outcomes Feedback Loop

```yaml
# Publicação de outcomes para treinamento RL
ML_ALLOCATION_OUTCOMES_ENABLED=true
ML_ALLOCATION_OUTCOMES_TOPIC=ml.allocation_outcomes
```

---

### Helm Values

**Arquivo**: `helm-charts/orchestrator-dynamic/values.yaml`

```yaml
config:
  optimizer:
    enabled: false  # Habilitar após validação
    endpoint: optimizer-agents.neural-hive-estrategica.svc.cluster.local:50051
    grpcTimeout: 10
    forecastHorizonMinutes: 60

  ml:
    localLoadPrediction:
      enabled: true
      cacheTtlSeconds: 30
      windowMinutes: 60
    allocationOutcomes:
      enabled: true
      topic: ml.allocation_outcomes
    optimizationTimeoutSeconds: 2
```

---

## Métricas Prometheus

### ML Optimization Metrics

| Métrica | Tipo | Descrição |
|---------|------|-----------|
| `orchestration_scheduler_ml_optimizations_applied_total{optimization_type, source}` | Counter | Total de otimizações ML aplicadas |
| `orchestration_scheduler_ml_optimization_latency_seconds` | Histogram | Latência de otimizações ML |
| `orchestration_scheduler_queue_prediction_error_ms` | Histogram | Erro de predição de queue time (ms) |
| `orchestration_scheduler_allocation_quality_score{used_ml_optimization}` | Histogram | Score de qualidade da alocação (0-1) |
| `orchestration_scheduler_optimizer_availability` | Gauge | Disponibilidade do optimizer-agents (0/1) |
| `orchestration_scheduler_predicted_queue_time_ms{source}` | Histogram | Queue times preditos (local/remote) |
| `orchestration_scheduler_predicted_worker_load_pct{source}` | Histogram | Worker load predito (0-1) |

### Labels

- **optimization_type**: `load_forecast`, `rl_recommendation`, `heuristic`
- **source**: `remote` (optimizer-agents), `local` (LoadPredictor), `fallback`
- **used_ml_optimization**: `true`, `false`

---

## Dashboards Grafana

### Dashboard Principal

**Arquivo**: `monitoring/dashboards/orchestrator-ml-scheduling-optimization.json`

**Painéis**:
1. **ML Optimization Success Rate**: Taxa de sucesso de otimizações ML (vs heurísticas)
2. **Optimizer Availability**: Disponibilidade do optimizer-agents remoto
3. **Allocation Quality Score (Median)**: Score mediano de qualidade de alocação
4. **ML Optimization Latency (P95)**: Latência P95 de otimizações
5. **Optimization Source Distribution**: Distribuição remote/local/fallback
6. **Queue Time Prediction Error (P95)**: Erro P95 de predições de queue
7. **Predicted vs Actual Queue Time**: Timeline de predições vs realidade
8. **ML Optimization Timeline (Last 24h)**: Tabela de otimizações por tipo/source

---

## Alertas Prometheus

**Arquivo**: `monitoring/alerts/orchestrator-ml-scheduling-alerts.yaml`

### Alertas Críticos

| Alerta | Condição | Severidade | Descrição |
|--------|----------|------------|-----------|
| `OptimizerAgentsDownExtended` | Optimizer indisponível >30min | Critical | Optimizer remoto inativo por período estendido |
| `QueuePredictionErrorCritical` | Erro P95 >30s por 5min | Critical | Erro crítico de predição de queue time |
| `MLOptimizationLatencyCritical` | Latência P95 >5s por 2min | Critical | Latência crítica de otimização ML |

### Alertas de Warning

| Alerta | Condição | Severidade | Descrição |
|--------|----------|------------|-----------|
| `OptimizerAgentsUnavailable` | Optimizer indisponível >5min | Warning | Optimizer remoto indisponível (usando fallback) |
| `MLOptimizationSuccessRateLow` | Taxa ML <50% por 10min | Warning | Alta taxa de fallback para heurísticas |
| `AllocationQualityScoreLow` | Score mediano <0.6 por 10min | Warning | Qualidade de alocação abaixo do esperado |
| `QueuePredictionsUsingDefaults` | Mediana = 1s ou P95 = 2s por 30min | Warning | Predições sempre retornando defaults (MongoDB pode estar indisponível) |

---

## RL Policy: Ações e Efeitos

O SchedulingOptimizer aplica **rl_boost** aos workers com base na **ação recomendada** pelo RL agent (Q-learning) do optimizer-agents.

### Ações RL

#### SCALE_UP

**Objetivo**: Distribuir carga, incentivar escalonamento horizontal

**Estratégia**:
- Workers com `predicted_load_pct < 0.3` recebem `rl_boost = 1.2` (20% boost)
- Workers com carga alta não recebem boost

**Efeito**: Scheduler prefere workers com baixa carga, distribuindo tarefas uniformemente.

#### CONSOLIDATE

**Objetivo**: Consolidar tarefas em workers ativos, otimizar utilização de recursos

**Estratégia**:
- Workers com `predicted_load_pct > 0.5` recebem `rl_boost = 1.1` (10% boost)
- Workers com carga baixa não recebem boost

**Efeito**: Scheduler prefere workers já carregados, consolidando execuções.

#### MAINTAIN

**Objetivo**: Manter comportamento padrão do scheduler

**Estratégia**:
- Todos workers recebem `rl_boost = 1.0` (sem boost)

**Efeito**: Score calculado normalmente, sem influência RL.

---

## Troubleshooting

### Optimizer Remoto Indisponível

**Sintomas**:
- Alerta `OptimizerAgentsUnavailable` disparado
- Métrica `orchestration_scheduler_optimizer_availability = 0`
- Logs: `"optimizer_client_not_available"` ou `"load_forecast_remote_unavailable"`

**Ação**:
1. Verificar status do pod `optimizer-agents`:
   ```bash
   kubectl get pods -n neural-hive-estrategica -l app=optimizer-agents
   kubectl logs -n neural-hive-estrategica deploy/optimizer-agents --tail=100
   ```
2. Validar conectividade gRPC:
   ```bash
   kubectl exec -n neural-hive-orchestration deploy/orchestrator-dynamic -- \
     grpcurl -plaintext optimizer-agents.neural-hive-estrategica.svc.cluster.local:50051 list
   ```
3. Sistema continua funcionando com **fallback local**, mas com qualidade reduzida de predições.

---

### Alta Taxa de Fallback para Heurísticas

**Sintomas**:
- Alerta `HighHeuristicFallbackRate` disparado
- Dashboard mostra >30% de otimizações com `source=fallback`

**Causas Possíveis**:
- MongoDB indisponível (LoadPredictor sem dados históricos)
- Redis indisponível (cache não funciona, forçando re-computação lenta)
- Optimizer remoto lento (timeout excedido)

**Ação**:
1. Verificar saúde do MongoDB:
   ```bash
   kubectl get pods -n mongodb-cluster -l app=mongodb
   ```
2. Verificar cache Redis:
   ```bash
   kubectl exec -n redis-cluster deploy/redis-cluster -- redis-cli ping
   ```
3. Ajustar timeout se optimizer está lento:
   ```yaml
   config:
     optimizer:
       grpcTimeout: 15  # Aumentar timeout
   ```

---

### Erro Alto de Predição de Queue Time

**Sintomas**:
- Alerta `QueuePredictionErrorHigh` ou `QueuePredictionErrorCritical`
- Dashboard mostra erro P95 >10s

**Causas Possíveis**:
- Dados históricos insuficientes (poucos tickets completados)
- Carga do sistema muito volátil (difícil de prever)
- Window de dados muito curto (`ml_local_load_window_minutes` muito baixo)

**Ação**:
1. Verificar volume de dados históricos:
   ```bash
   mongo neural_hive_orchestration --eval 'db.execution_tickets.countDocuments({status: "COMPLETED"})'
   ```
2. Aumentar janela de dados:
   ```yaml
   config:
     ml:
       localLoadPrediction:
         windowMinutes: 120  # Aumentar de 60 para 120 minutos
   ```
3. Validar que `actual_duration_ms` está sendo registrado corretamente nos tickets completados.

---

### Predições Sempre Retornando Defaults

**Sintomas**:
- Alerta `QueuePredictionsUsingDefaults` disparado
- Logs: `"fetch_completions_skipped_no_mongodb"` ou `"queue_depth_estimation_skipped_no_mongodb"`

**Causa**:
- MongoDB indisponível ou LoadPredictor rodando em **modo degradado**

**Ação**:
1. Verificar inicialização do orchestrator:
   ```bash
   kubectl logs -n neural-hive-orchestration deploy/orchestrator-dynamic | grep "degraded"
   ```
2. Se `"mode=degraded"`, MongoDB não foi inicializado corretamente. Verificar variável `MONGODB_URI`.
3. Restart do orchestrator após corrigir MongoDB:
   ```bash
   kubectl rollout restart deploy/orchestrator-dynamic -n neural-hive-orchestration
   ```

---

## Estratégia de Rollout

### Fase 1: Validação em Staging (Local Only)

1. Habilitar apenas **LoadPredictor local**:
   ```yaml
   config:
     optimizer:
       enabled: false  # Optimizer remoto OFF
     ml:
       localLoadPrediction:
         enabled: true  # Local ON
   ```

2. Monitorar métricas:
   - `orchestration_scheduler_predicted_queue_time_ms{source="local"}`
   - `orchestration_scheduler_allocation_quality_score{used_ml_optimization="true"}`

3. Validar que não há degradação de latência (<50ms overhead).

---

### Fase 2: Validação em Staging (Remote + Local)

1. Deploy do `optimizer-agents` em staging.
2. Habilitar **integração remota**:
   ```yaml
   config:
     optimizer:
       enabled: true
       endpoint: optimizer-agents.neural-hive-estrategica.svc.cluster.local:50051
   ```

3. Monitorar:
   - `orchestration_scheduler_optimizer_availability` (deve ser 1)
   - `orchestration_scheduler_ml_optimization_latency_seconds` (P95 <2s)
   - Taxa de uso remote vs local vs fallback

4. Comparar **allocation quality score** com e sem ML.

---

### Fase 3: Rollout em Produção

1. Deploy gradual com Canary (10% → 50% → 100%):
   ```yaml
   replicaCount: 2
   autoscaling:
     enabled: true
     minReplicas: 2
   ```

2. Habilitar **allocation outcomes feedback**:
   ```yaml
   config:
     ml:
       allocationOutcomes:
         enabled: true  # Publicar outcomes para treinamento RL
   ```

3. Monitorar SLA compliance e throughput:
   - Comparar com baseline sem ML
   - Validar que não há regressão em `orchestration_sla_violations_total`

4. Ajustar pesos de scoring se necessário:
   ```yaml
   config:
     ml:
       localLoadPrediction:
         queuePredictionWeight: 0.25  # Aumentar peso de queue time
         loadPredictionWeight: 0.15   # Aumentar peso de carga
   ```

---

## Testes

### Testes Unitários

**Localização**: `tests/unit/`

- `test_load_predictor.py`: Testes de predição local (cache, histórico, fallback)
- `test_scheduling_optimizer.py`: Testes de otimização (remote, local, RL boost, feedback loop)

**Executar**:
```bash
cd services/orchestrator-dynamic
pytest tests/unit/test_load_predictor.py -v
pytest tests/unit/test_scheduling_optimizer.py -v
```

---

### Testes de Integração

**Localização**: `tests/integration/`

- `test_ml_scheduling_integration.py`: Testes end-to-end (LoadPredictor + SchedulingOptimizer + ResourceAllocator)

**Cenários**:
- Fluxo completo com ML optimization
- Fallback quando optimizer indisponível
- Modo degradado sem MongoDB
- Feedback loop de allocation outcomes

**Executar**:
```bash
pytest tests/integration/test_ml_scheduling_integration.py -v
```

---

## Referências

- **Prophet**: [facebook/prophet](https://github.com/facebook/prophet) - Time series forecasting
- **Q-learning**: Reinforcement Learning para decisões de scheduling
- **Exponential Smoothing**: Técnica de suavização de séries temporais
- **Moving Averages**: Média móvel para predição de duração

---

## Changelog

### v1.0.9 (2025-01-17)

- ✅ Implementação completa do ML Scheduling Optimization
- ✅ RL boost scoring no ResourceAllocator
- ✅ Tratamento de MongoDB None (modo degradado)
- ✅ Registro de métricas de predição (queue time e worker load)
- ✅ Dashboards Grafana e alertas Prometheus
- ✅ Testes unitários e de integração
- ✅ Documentação completa
