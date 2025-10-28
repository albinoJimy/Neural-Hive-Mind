# Neural Hive Mind - Observabilidade

Este diretório contém configurações e dashboards para observabilidade completa do Neural Hive Mind.

## Componentes

### 1. Métricas Agregadas

**Localização:** `libraries/python/neural_hive_specialists/observability/aggregated_metrics.py`

Coleta métricas de alto nível:
- `neural_hive_ledger_health_score` - Score geral de saúde (0.0-1.0)
- `neural_hive_consensus_rate` - Taxa de consenso entre especialistas
- `neural_hive_avg_confidence_by_specialist` - Confiança média por especialista
- `neural_hive_avg_risk_by_specialist` - Risco médio por especialista
- `neural_hive_specialist_agreement_score` - Concordância entre pares de especialistas
- `neural_hive_opinion_latency_p50/p95/p99_ms` - Latências de processamento
- `neural_hive_recommendation_distribution_pct` - Distribuição de recomendações
- `neural_hive_high_risk_opinions_rate` - Taxa de opiniões de alto risco
- `neural_hive_buffered_opinions_rate` - Taxa de bufferização por indisponibilidade
- `neural_hive_total_opinions_24h` - Total de opiniões nas últimas 24h
- `neural_hive_ledger_growth_rate_per_hour` - Taxa de crescimento do ledger
- `neural_hive_masked_documents_rate` - Taxa de documentos mascarados (compliance)

**Uso:**

```python
from neural_hive_specialists.observability import AggregatedMetricsCollector
import asyncio

config = {
    'mongodb_uri': 'mongodb://localhost:27017',
    'mongodb_database': 'neural_hive',
    'metrics_window_hours': 24
}

collector = AggregatedMetricsCollector(config)

# Coletar métricas (executar periodicamente via scheduler)
asyncio.run(collector.collect_all_metrics())

# Obter resumo de saúde
health_summary = collector.get_system_health_summary()
print(health_summary)

# Calcular matriz de concordância
agreement_matrix = collector.calculate_specialist_agreement_matrix()
```

### 2. Health Checks Avançados

**Localização:** `libraries/python/neural_hive_specialists/observability/health_checks.py`

Verifica saúde de componentes individuais:
- MongoDB (latência, disponibilidade)
- MLflow (conectividade, modelos registrados)
- Feature Extraction (ontologias, embeddings)
- Circuit Breakers (estado, configuração)
- Ledger (taxa de bufferização, documentos recentes)

**Uso:**

```python
from neural_hive_specialists.observability import SpecialistHealthChecker
import asyncio

config = {
    'mongodb_uri': 'mongodb://localhost:27017',
    'mlflow_tracking_uri': 'http://localhost:5000',
    'enable_circuit_breaker': True
}

health_checker = SpecialistHealthChecker(config, specialist_type='technical')

# Verificar saúde de todos os componentes
health_report = asyncio.run(health_checker.check_all_health())

print(f"Overall Status: {health_report['overall_status']}")
print(f"Components: {health_report['summary']}")

# Exemplo de saída:
# {
#   "overall_status": "healthy",
#   "specialist_type": "technical",
#   "checked_at": "2025-10-10T12:00:00Z",
#   "components": [
#     {
#       "component": "mongodb",
#       "status": "healthy",
#       "message": "MongoDB operational",
#       "latency_ms": 15.2
#     },
#     ...
#   ]
# }
```

### 3. Dashboards Grafana

**Localização:** `observability/grafana-dashboards/`

#### Dashboard 1: Neural Hive Overview
**Arquivo:** `neural-hive-overview.json`

Visualizações:
- Ledger Health Score (gauge)
- Consensus Rate (gauge)
- Evaluations Rate (timeseries)
- Average Confidence by Specialist (timeseries)
- Average Risk by Specialist (timeseries)
- Recommendation Distribution (pie chart)
- Opinion Latency P50/P95/P99 (timeseries)
- High Risk Rate (gauge)
- Total Opinions 24h (timeseries)
- Ledger Growth Rate (timeseries)

**Importação:**
1. Abrir Grafana (http://localhost:3000)
2. Ir em Dashboards → Import
3. Upload do arquivo `neural-hive-overview.json`
4. Selecionar Prometheus datasource
5. Clicar em Import

#### Dashboard 2: Specialist ML Metrics
**Arquivo:** `specialist-ml-metrics.json`

Visualizações (por especialista):
- Model Inference Latency P50/P95/P99
- Model Inference Status Rate (success/timeout/error)
- Model Fallback Rate
- Feature Extraction Duration
- Feature Vector Size
- Inference Status Distribution
- Circuit Breaker States
- Fallback Invocations Rate

**Variável de Template:**
- `$specialist_type` - Dropdown para selecionar especialista (technical, business, behavior, evolution, architecture)

**Importação:**
1. Abrir Grafana (http://localhost:3000)
2. Ir em Dashboards → Import
3. Upload do arquivo `specialist-ml-metrics.json`
4. Selecionar Prometheus datasource
5. Clicar em Import

### 4. Alertas Prometheus

**Localização:** `observability/prometheus-alerts/neural-hive-alerts.yaml`

#### Grupos de Alertas

**1. neural_hive_slos** - Alertas baseados em SLOs
- `LedgerHealthScoreLow` - Health score < 0.7 por 5min
- `LedgerHealthScoreCritical` - Health score < 0.5 por 2min
- `ConsensusRateLow` - Consensus < 0.6 por 10min
- `HighRiskRateElevated` - High risk > 15% por 15min
- `HighRiskRateCritical` - High risk > 30% por 5min
- `SpecialistConfidenceLow` - Confiança < 0.5 por 10min
- `ModelInferenceFailureRateHigh` - Falhas > 5% por 5min
- `ModelInferenceLatencyHigh` - P95 > 3s por 5min
- `FeatureExtractionSlow` - P95 > 1s por 5min
- `BufferedOpinionsRateHigh` - Bufferização > 10% por 10min
- `OpinionLatencyHigh` - P95 > 5s por 5min
- `CircuitBreakerOpenTooLong` - Aberto por > 10min
- `FallbackRateHigh` - Taxa > 0.1/s por 5min
- `LedgerGrowthRateAnomaly` - Crescimento > 2x média
- `LedgerGrowthRateLow` - Crescimento < 1 opinião/hora por 30min
- `SpecialistDisagreementHigh` - Agreement < 0.4 por 15min
- `MaskedDocumentsRateHigh` - Mascaramento > 50%

**2. neural_hive_availability** - Alertas de disponibilidade
- `NoEvaluationsProcessed` - Nenhuma avaliação em 5min
- `EvaluationErrorRateHigh` - Taxa de erro > 10% por 5min

**3. neural_hive_security** - Alertas de segurança
- `AuthenticationFailureRateHigh` - Falhas auth > 5% por 5min
- `AuthenticationSpikeDetected` - Spike 3x média de 30min

#### Configuração Prometheus

**1. Adicionar regras de alerta ao Prometheus**

Editar `prometheus.yml`:

```yaml
rule_files:
  - /etc/prometheus/alerts/neural-hive-alerts.yaml

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - localhost:9093
```

**2. Verificar regras carregadas:**

```bash
curl http://localhost:9090/api/v1/rules | jq
```

**3. Verificar alertas ativos:**

```bash
curl http://localhost:9090/api/v1/alerts | jq
```

#### Configuração Alertmanager

**Exemplo de configuração (alertmanager.yml):**

```yaml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'specialist_type']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'neural-hive-alerts'
  routes:
    - match:
        severity: critical
      receiver: 'critical-alerts'
      continue: true

receivers:
  - name: 'neural-hive-alerts'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK'
        channel: '#neural-hive-alerts'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'

  - name: 'critical-alerts'
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_KEY'

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'specialist_type']
```

## Deployment

### 1. Configurar Coletor de Métricas Periódico

**Opção A: APScheduler (Python)**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from neural_hive_specialists.observability import AggregatedMetricsCollector
import asyncio

config = {...}
collector = AggregatedMetricsCollector(config)

scheduler = AsyncIOScheduler()

# Coletar métricas a cada 60 segundos
scheduler.add_job(
    collector.collect_all_metrics,
    'interval',
    seconds=60,
    id='collect_metrics'
)

scheduler.start()

# Manter rodando
asyncio.get_event_loop().run_forever()
```

**Opção B: Kubernetes CronJob**

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: neural-hive-metrics-collector
spec:
  schedule: "*/1 * * * *"  # A cada 1 minuto
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: metrics-collector
            image: neural-hive/metrics-collector:latest
            command: ["python", "-m", "neural_hive_specialists.observability.collector"]
          restartPolicy: OnFailure
```

### 2. Expor Health Check Endpoint

**Integrar com gRPC Health Check:**

```python
from neural_hive_specialists.observability import SpecialistHealthChecker
import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

class HealthServicer(health_pb2_grpc.HealthServicer):
    def __init__(self, config, specialist_type):
        self.health_checker = SpecialistHealthChecker(config, specialist_type)

    async def Check(self, request, context):
        health_report = await self.health_checker.check_all_health()

        if health_report['overall_status'] == 'healthy':
            return health_pb2.HealthCheckResponse(
                status=health_pb2.HealthCheckResponse.SERVING
            )
        else:
            return health_pb2.HealthCheckResponse(
                status=health_pb2.HealthCheckResponse.NOT_SERVING
            )

# Adicionar ao servidor gRPC
health_servicer = HealthServicer(config, 'technical')
health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
```

### 3. Integrar com Kubernetes Probes

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: specialist-technical
spec:
  containers:
  - name: specialist
    image: neural-hive/specialist-technical:latest
    livenessProbe:
      grpc:
        port: 50051
        service: grpc.health.v1.Health
      initialDelaySeconds: 30
      periodSeconds: 10
    readinessProbe:
      grpc:
        port: 50051
        service: grpc.health.v1.Health
      initialDelaySeconds: 10
      periodSeconds: 5
```

## SLOs Definidos

| Métrica | SLO | Alerta Warning | Alerta Critical |
|---------|-----|----------------|-----------------|
| Ledger Health Score | > 0.7 | < 0.7 por 5min | < 0.5 por 2min |
| Consensus Rate | > 0.6 | < 0.6 por 10min | - |
| High Risk Rate | < 15% | > 15% por 15min | > 30% por 5min |
| Specialist Confidence | > 0.5 | < 0.5 por 10min | - |
| Model Inference Success | > 95% | < 95% por 5min | - |
| Model Inference Latency P95 | < 3s | > 3s por 5min | - |
| Feature Extraction P95 | < 1s | > 1s por 5min | - |
| Buffered Rate | < 10% | > 10% por 10min | - |
| Opinion Latency P95 | < 5s | > 5s por 5min | - |
| Evaluation Error Rate | < 10% | > 10% por 5min | - |
| Auth Failure Rate | < 5% | > 5% por 5min | - |

## Troubleshooting

### Health Check retornando DEGRADED

1. Verificar logs do especialista
2. Verificar métricas de circuit breakers
3. Verificar conectividade com MongoDB/MLflow
4. Verificar taxa de bufferização

### Alertas de latência alta

1. Verificar carga do sistema
2. Verificar performance do MongoDB
3. Verificar timeouts de inferência de modelo
4. Verificar feature extraction (embeddings)

### Consensus rate baixo

1. Verificar configurações dos especialistas
2. Analisar matriz de concordância entre especialistas
3. Revisar planos cognitivos com divergência
4. Verificar calibração dos modelos

### Circuit breakers abertos

1. Verificar disponibilidade das dependências
2. Verificar logs de erros
3. Verificar métricas de fallback
4. Considerar ajustar thresholds de circuit breaker

## Referências

- [Prometheus Alerting](https://prometheus.io/docs/alerting/latest/overview/)
- [Grafana Dashboards](https://grafana.com/docs/grafana/latest/dashboards/)
- [gRPC Health Checking](https://github.com/grpc/grpc/blob/master/doc/health-checking.md)
- [SLO Best Practices](https://sre.google/workbook/implementing-slos/)
