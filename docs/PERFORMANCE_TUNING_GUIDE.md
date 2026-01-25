# Guia de Tuning de Performance - Fluxo C

Este documento descreve como executar testes de carga, interpretar resultados e ajustar parametros de performance para o Fluxo C de Orquestracao.

## Arquitetura do Fluxo C

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│     C1      │────>│     C2      │────>│     C3      │────>│     C4      │
│  Validate   │     │   Generate  │     │  Discover   │     │   Assign    │
│  Decision   │     │   Tickets   │     │   Workers   │     │   Tickets   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                   │
                    ┌─────────────┐     ┌─────────────┐           │
                    │     C6      │<────│     C5      │<──────────┘
                    │   Publish   │     │   Monitor   │
                    │  Telemetry  │     │  Execution  │
                    └─────────────┘     └─────────────┘
```

## Performance Baselines

| Metrica | Target | Warning | Critico |
|---------|--------|---------|---------|
| Latencia P95 E2E | < 4h | > 3h | > 4h |
| Latencia P99 E2E | < 6h | > 5h | > 6h |
| Throughput | > 10 tickets/s | < 15/s | < 10/s |
| Taxa de Sucesso | > 99% | < 99.5% | < 99% |
| CPU Orchestrator | < 70% | > 70% | > 85% |
| Memoria Orchestrator | < 75% | > 75% | > 85% |

## Executando Testes de Carga

### Execucao Local

```bash
# Teste basico (100 workflows)
pytest tests/performance/test_flow_c_load.py -v -m performance

# Teste com configuracao customizada
WORKFLOWS_COUNT=200 CONCURRENT_WORKFLOWS=100 \
  pytest tests/performance/test_flow_c_load.py::TestFlowCThroughput -v

# Teste de autoscaling (mais longo)
pytest tests/performance/test_flow_c_load.py::TestFlowCAutoscaling -v -m slow

# Gerar relatorio
python -c "
from tests.performance.report_generator import generate_performance_report
# ... executar apos testes
"
```

### Via GitHub Actions

```bash
# Disparar workflow manual
gh workflow run performance-test.yml \
  -f workflows_count=100 \
  -f concurrent=50
```

### Via kubectl (CronJob)

```bash
# Criar job ad-hoc
kubectl create job --from=cronjob/flow-c-performance-test \
  flow-c-perf-$(date +%Y%m%d-%H%M%S) \
  -n neural-hive-orchestration
```

## Parametros de Tuning

### Autoscaling (HPA)

Localizado em `helm-charts/orchestrator-dynamic/values.yaml`:

```yaml
autoscaling:
  enabled: true
  minReplicas: 2        # Minimo de replicas
  maxReplicas: 10       # Maximo de replicas
  targetCPUUtilizationPercentage: 70     # Scale-up quando CPU > 70%
  targetMemoryUtilizationPercentage: 80  # Scale-up quando memoria > 80%
```

**Recomendacoes:**
- **Alta carga (> 50 workflows/s):** Aumentar `minReplicas` para 5
- **Picos de carga:** Reduzir `targetCPUUtilizationPercentage` para 60%
- **Economia de recursos:** Aumentar targets para 80%/90%

### Resources

```yaml
resources:
  requests:
    cpu: 400m       # Request minimo de CPU
    memory: 1Gi     # Request minimo de memoria
  limits:
    cpu: 1600m      # Limite de CPU
    memory: 3Gi     # Limite de memoria
```

**Recomendacoes:**
- **CPU saturada:** Aumentar limit para 2000m ou 3200m
- **OOM frequente:** Aumentar memory limit para 4Gi ou 6Gi
- **Custo elevado:** Reduzir requests (nao limits)

### Scheduler

```yaml
config:
  scheduler:
    enableIntelligentScheduler: true
    enableMlEnhancedScheduling: true
    maxParallelTickets: 100  # Tickets simultaneos
```

**Recomendacoes:**
- **Throughput baixo:** Aumentar `maxParallelTickets` para 200
- **Latencia alta:** Reduzir para 50-75 para evitar sobrecarga

### MongoDB

```yaml
config:
  mongodb:
    maxPoolSize: 100   # Conexoes no pool
    minPoolSize: 10    # Conexoes minimas
```

**Recomendacoes:**
- **Pool saturado (> 90%):** Aumentar para 200
- **Conexoes ociosas:** Reduzir `minPoolSize` para 5

### Kafka

```yaml
config:
  kafka:
    # Particoes sao configuradas no topico
```

**Recomendacoes:**
- **Lag alto:** Aumentar particoes (requer recriacao do topico)
- **Throughput baixo:** Verificar `batch.size` e `linger.ms`

### Circuit Breakers

```yaml
config:
  circuitBreaker:
    enabled: true
    failMax: 5              # Falhas para abrir
    timeoutSeconds: 60      # Tempo aberto
    recoveryTimeoutSeconds: 30  # Tempo em half-open
```

**Recomendacoes:**
- **Abrindo muito rapido:** Aumentar `failMax` para 10
- **Recovery muito lento:** Reduzir `recoveryTimeoutSeconds` para 15

## Resolucao de Bottlenecks

### CPU Saturada (> 85%)

**Sintomas:**
- Latencia crescente
- Requests timeout
- HPA nao consegue escalar rapido o suficiente

**Solucoes:**
1. Aumentar `resources.limits.cpu` de 1600m para 2000m
2. Reduzir `targetCPUUtilizationPercentage` para 60%
3. Aumentar `maxReplicas` para 15

### Memoria Elevada (> 85%)

**Sintomas:**
- OOM kills
- Pods evicted
- Restarts frequentes

**Solucoes:**
1. Aumentar `resources.limits.memory` para 4Gi
2. Verificar memory leaks no codigo
3. Habilitar GC mais agressivo

### Kafka Lag Alto (> 1000)

**Sintomas:**
- Delay entre producao e consumo
- Backpressure
- Throughput reduzido

**Solucoes:**
1. Aumentar particoes do topico
2. Adicionar mais replicas (consumers)
3. Otimizar processamento de mensagens

### MongoDB Pool Saturado (> 90%)

**Sintomas:**
- Connection timeout
- Queries lentas
- Erros de "pool exhausted"

**Solucoes:**
1. Aumentar `maxPoolSize` de 100 para 200
2. Otimizar queries (indices, projecoes)
3. Usar `readPreference: secondaryPreferred`

### Temporal Queue Profunda (> 1000)

**Sintomas:**
- Workflows atrasados
- Activities acumulando
- Timeout de activities

**Solucoes:**
1. Aumentar workers Temporal
2. Otimizar duracao de activities
3. Revisar timeouts de activities

## Monitoramento Durante Testes

### Dashboards Grafana

- **Orchestrator Overview:** Metricas gerais
- **Flow C Pipeline:** Latencia por step
- **Autoscaling:** HPA e replicas

### Comandos Uteis

```bash
# Watch HPA
kubectl get hpa orchestrator-dynamic -n neural-hive-orchestration -w

# Watch pods
watch -n 5 'kubectl get pods -n neural-hive-orchestration \
  -l app.kubernetes.io/name=orchestrator-dynamic'

# Logs em tempo real
kubectl logs -f -n neural-hive-orchestration \
  -l app.kubernetes.io/name=orchestrator-dynamic --tail=100

# Query Prometheus
curl -G 'http://prometheus:9090/api/v1/query' \
  --data-urlencode 'query=histogram_quantile(0.95, rate(neural_hive_flow_c_duration_seconds_bucket[5m]))'
```

## Cenarios de Tuning

### Cenario: Alta Carga (> 50 workflows/s)

```yaml
autoscaling:
  minReplicas: 5
  maxReplicas: 20
  targetCPUUtilizationPercentage: 60

resources:
  requests:
    cpu: 800m
    memory: 2Gi
  limits:
    cpu: 3200m
    memory: 6Gi

config:
  mongodb:
    maxPoolSize: 200
  scheduler:
    maxParallelTickets: 200
```

### Cenario: Baixa Latencia (P95 < 2h)

```yaml
autoscaling:
  minReplicas: 4
  maxReplicas: 15
  targetCPUUtilizationPercentage: 50

config:
  scheduler:
    maxParallelTickets: 50  # Reduzir paralelismo
  retry:
    maxAttempts: 2  # Menos retries
```

### Cenario: Economia de Recursos

```yaml
autoscaling:
  minReplicas: 2
  maxReplicas: 8
  targetCPUUtilizationPercentage: 80
  targetMemoryUtilizationPercentage: 85

resources:
  requests:
    cpu: 200m
    memory: 512Mi
  limits:
    cpu: 1000m
    memory: 2Gi
```

## Alertas Relevantes

Os alertas estao definidos em `monitoring/alerts/flow-c-integration-alerts.yaml`:

| Alerta | Condicao | Severidade |
|--------|----------|------------|
| FlowCLatencyHigh | P95 > 4h | critical |
| FlowCSuccessRateLow | < 99% | critical |
| FlowCThroughputLow | < 10/s | warning |
| OrchestratorCPUHigh | > 85% | warning |
| OrchestratorMemoryHigh | > 85% | warning |
| CircuitBreakerOpen | estado = open | critical |

## Referencias

- [Test Files](../tests/performance/test_flow_c_load.py)
- [Values.yaml](../helm-charts/orchestrator-dynamic/values.yaml)
- [Flow C Alerts](../monitoring/alerts/flow-c-integration-alerts.yaml)
- [Phase 2 Integration](./PHASE2_FLOW_C_INTEGRATION.md)
