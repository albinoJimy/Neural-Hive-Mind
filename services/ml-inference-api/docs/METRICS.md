# Metrics Documentation - ML Inference API

Documentação completa de métricas Prometheus, queries Grafana e alertas configurados.

## Índice

- [Visão Geral](#visão-geral)
- [Métricas Disponíveis](#métricas-disponíveis)
- [Acesso às Métricas](#accesso-as-métricas)
- [Queries Grafana](#queries-grafana)
- [Dashboards](#dashboards)
- [Alertas](#alertas)
- [Boas Práticas](#boas-práticas)

---

## Visão Geral

O ML Inference API expõe métricas em formato Prometheus na porta `9091` (configurável via `PROMETHEUS_PORT`).

### Tipos de Métricas

- **Counter:** Valor que só aumenta (ex: total de requests)
- **Gauge:** Valor que pode subir ou descer (ex: memória usada)
- **Histogram:** Distribuição de valores (ex: latência)
- **Summary:** Estatísticas (ex: média, percentis)
- **Info:** Informações estáticas (ex: versão do serviço)

### Endpoint

```
http://localhost:8010/metrics
```

---

## Métricas Disponíveis

### Métricas de Serviço

#### service_info

Informações estáticas sobre o serviço.

```promql
# Tipo: Info
service_info{name="ml-inference-api",version="1.0.0"}
```

### Métricas de Modelo

#### model_loaded

Indica se o modelo ML está carregado.

```promql
# Tipo: Gauge
# Valores: 0 = não carregado, 1 = carregado
model_loaded
```

#### model_loading_duration_seconds

Distribuição do tempo de carregamento do modelo.

```promql
# Tipo: Histogram
model_loading_duration_seconds_bucket
model_loading_duration_seconds_sum
model_loading_duration_seconds_count
```

#### model_version_info

Informações sobre a versão do modelo carregado.

```promql
# Tipo: Info
model_version_info{version="v7",type="GradientBoostingClassifier",path="/app/ml_models/..."}
```

### Métricas de Inferência

#### predictions_total

Total de predições realizadas, por tipo de decisão.

```promql
# Tipo: Counter
# Labels: decision (approve, reject, review_required)
predictions_total{decision="approve"}
predictions_total{decision="reject"}
predictions_total{decision="review_required"}
```

#### prediction_duration_seconds

Distribuição da duração das predições.

```promql
# Tipo: Histogram
# Buckets: 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0
prediction_duration_seconds_bucket{le="0.1"}
prediction_duration_seconds_sum
prediction_duration_seconds_count
```

#### prediction_confidence

Distribuição das confianças das predições.

```promql
# Tipo: Histogram
# Buckets: 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0
prediction_confidence_bucket{le="0.8"}
prediction_confidence_sum
prediction_confidence_count
```

### Métricas de Batch

#### batch_predictions_total

Total de batches processados.

```promql
# Tipo: Counter
batch_predictions_total
```

#### batch_size

Distribuição do tamanho dos batches processados.

```promql
# Tipo: Histogram
# Buckets: 1, 5, 10, 25, 50, 75, 100
batch_size_bucket{le="10"}
batch_size_sum
batch_size_count
```

#### batch_duration_seconds

Distribuição da duração do processamento em batch.

```promql
# Tipo: Histogram
batch_duration_seconds_bucket
batch_duration_seconds_sum
batch_duration_seconds_count
```

#### batch_avg_latency_ms

Latência média por item em batch (Summary).

```promql
# Tipo: Summary
batch_avg_latency_ms_count
batch_avg_latency_ms_sum
```

### Métricas de API

#### api_requests_total

Total de requests REST API.

```promql
# Tipo: Counter
# Labels: method, endpoint, status_code
api_requests_total{method="POST",endpoint="/api/v1/inference/predict",status_code="200"}
api_requests_total{method="GET",endpoint="/health",status_code="200"}
api_requests_total{method="POST",endpoint="/api/v1/inference/predict",status_code="500"}
```

#### api_request_duration_seconds

Latência de requests da API.

```promql
# Tipo: Histogram
# Buckets: 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0
api_request_duration_seconds_bucket{le="0.1"}
api_request_duration_seconds_sum
api_request_duration_seconds_count
```

#### api_errors_total

Total de erros na API.

```promql
# Tipo: Counter
# Labels: endpoint, error_type
api_errors_total{endpoint="/api/v1/inference/predict",error_type="circuit_breaker_open"}
api_errors_total{endpoint="/api/v1/inference/predict",error_type="validation_error"}
```

### Métricas de Circuit Breaker

#### circuit_breaker_state

Estado atual do circuit breaker.

```promql
# Tipo: Gauge
# Valores: 0 = CLOSED, 1 = OPEN, 2 = HALF_OPEN
circuit_breaker_state
```

#### circuit_breaker_failures_total

Total de falhas que triggeraram o circuit breaker.

```promql
# Tipo: Counter
circuit_breaker_failures_total
```

#### circuit_breaker_recoveries_total

Total de recuperações do circuit breaker.

```promql
# Tipo: Counter
circuit_breaker_recoveries_total
```

### Métricas de Rate Limiting

#### rate_limit_hits_total

Total de requests bloqueados por rate limit.

```promql
# Tipo: Counter
rate_limit_hits_total
```

### Métricas de Cache (se implementado)

#### cache_hits_total

Total de cache hits.

```promql
# Tipo: Counter
# Labels: cache_type
cache_hits_total{cache_type="prediction"}
```

#### cache_misses_total

Total de cache misses.

```promql
# Tipo: Counter
# Labels: cache_type
cache_misses_total{cache_type="prediction"}
```

---

## Acesso às Métricas

### cURL

```bash
# Métricas em texto
curl http://localhost:8010/metrics

# Apenas predições
curl http://localhost:8010/metrics | grep predictions_total

# Apenas histogramas
curl http://localhost:8010/metrics | grep _bucket
```

### Prometheus

Configurar scrape no `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'ml-inference-api'
    static_configs:
      - targets: ['ml-inference-api:9091']
    scrape_interval: 15s
    metrics_path: /metrics
```

---

## Queries Grafana

### Overview

#### Requests por Segundo (RPS)

```promql
sum(rate(api_requests_total[1m])) by (endpoint)
```

#### Taxa de Erros

```promql
sum(rate(api_requests_total{status_code=~"5.."}[5m])) /
sum(rate(api_requests_total[5m])) * 100
```

### Inferência

#### Taxa de Predições

```promql
sum(rate(predictions_total[1m])) by (decision)
```

#### Latência P95 de Predição

```promql
histogram_quantile(0.95,
  sum(rate(prediction_duration_seconds_bucket[5m])) by (le)
)
```

#### Latência Média de Predição

```promql
sum(rate(prediction_duration_seconds_sum[5m])) /
sum(rate(prediction_duration_seconds_count[5m]))
```

#### Distribuição de Confiança

```promql
sum(rate(prediction_confidence_bucket[5m])) by (le)
```

### Batch

#### Tamanho Médio de Batch

```promql
sum(rate(batch_size_sum[5m])) /
sum(rate(batch_size_count[5m]))
```

#### Throughput de Batch

```promql
sum(rate(batch_predictions_total[1m]))
```

### Circuit Breaker

#### Estado Atual

```promql
circuit_breaker_state
# 0 = CLOSED, 1 = OPEN, 2 = HALF_OPEN
```

#### Taxa de Abertura

```promql
rate(circuit_breaker_failures_total[5m])
```

#### Tempo Desde Abertura

```promql
time() - (
  max(circuit_breaker_opened_timestamp) or vector(0)
)
```

### Saúde do Modelo

#### Modelo Carregado

```promql
model_loaded
# 1 = carregado, 0 = não carregado
```

#### Tempo de Carregamento

```promql
model_loading_duration_seconds_bucket
```

### Rate Limiting

#### Taxa de Rate Limit Hits

```promql
rate(rate_limit_hits_total[1m])
```

### Combinadas

#### Predições vs Erros (gráfico combinado)

```promql
# Predições bem-sucedidas
sum(rate(predictions_total[1m]))

# Erros de API
sum(rate(api_errors_total[1m]))
```

#### Ratio Approve/Reject

```promql
sum(rate(predictions_total{decision="approve"}[5m])) /
sum(rate(predictions_total{decision="reject"}[5m]))
```

---

## Dashboards

### Dashboard JSON (Grafana)

Importar este dashboard no Grafana:

```json
{
  "dashboard": {
    "title": "ML Inference API",
    "tags": ["ml", "inference", "neural-hive-mind"],
    "timezone": "browser",
    "panels": [
      {
        "title": "Requests por Segundo",
        "type": "graph",
        "targets": [
          {
            "expr": "sum(rate(api_requests_total[1m])) by (endpoint)"
          }
        ]
      },
      {
        "title": "Taxa de Erros (%)",
        "type": "graph",
        "targets": [
          {
            "expr": "sum(rate(api_requests_total{status_code=~\"5..\"}[5m])) / sum(rate(api_requests_total[5m])) * 100"
          }
        ]
      },
      {
        "title": "Predições por Decisão",
        "type": "graph",
        "targets": [
          {
            "expr": "sum(rate(predictions_total[1m])) by (decision)"
          }
        ]
      },
      {
        "title": "Latência P95 (ms)",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, sum(rate(prediction_duration_seconds_bucket[5m])) by (le)) * 1000"
          }
        ]
      },
      {
        "title": "Estado do Circuit Breaker",
        "type": "stat",
        "targets": [
          {
            "expr": "circuit_breaker_state"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "mappings": [
              {"value": 0, "text": "CLOSED"},
              {"value": 1, "text": "OPEN"},
              {"value": 2, "text": "HALF_OPEN"}
            ]
          }
        }
      },
      {
        "title": "Modelo Carregado",
        "type": "stat",
        "targets": [
          {
            "expr": "model_loaded"
          }
        ]
      },
      {
        "title": "Distribuição de Confiança",
        "type": "heatmap",
        "targets": [
          {
            "expr": "sum(rate(prediction_confidence_bucket[5m])) by (le)"
          }
        ]
      },
      {
        "title": "Taxa de Rate Limit Hits",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(rate_limit_hits_total[1m])"
          }
        ]
      }
    ]
  }
}
```

### Layout Sugerido

```
┌─────────────────────────────────────────────────────────────┐
│                    ML Inference API                          │
├──────────────────┬──────────────────┬────────────────────────┤
│ Requests/sec     │ Taxa de Erros    │ Predições/Decisão      │
├──────────────────┴──────────────────┴────────────────────────┤
│                        Latência P95                          │
├──────────────────┬──────────────────┬────────────────────────┤
│ Circuit Breaker  │ Modelo Carregado │ Rate Limit Hits        │
├──────────────────┴──────────────────┴────────────────────────┤
│                    Distribuição de Confiança                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Alertas

### Regras Prometheus (Alertmanager)

```yaml
groups:
  - name: ml_inference_api
    interval: 30s
    rules:
      # Modelo não carregado
      - alert: MLModelNotLoaded
        expr: model_loaded == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Modelo ML não carregado"
          description: "O modelo ML não está carregado há mais de 1 minuto"

      # Circuit breaker aberto
      - alert: CircuitBreakerOpen
        expr: circuit_breaker_state == 1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Circuit breaker aberto"
          description: "O circuit breaker está aberto há mais de 2 minutos"

      # Alta taxa de erros
      - alert: HighErrorRate
        expr: |
          sum(rate(api_requests_total{status_code=~"5.."}[5m])) /
          sum(rate(api_requests_total[5m])) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Alta taxa de erros"
          description: "Taxa de erros acima de 5% nos últimos 5 minutos"

      # Latência alta
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95,
            sum(rate(prediction_duration_seconds_bucket[5m])) by (le)
          ) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Alta latência de predição"
          description: "Latência P95 acima de 1 segundo nos últimos 5 minutos"

      # Rate limit hits
      - alert: HighRateLimitHits
        expr: rate(rate_limit_hits_total[1m]) > 10
        for: 5m
        labels:
          severity: info
        annotations:
          summary: "Muitos rate limit hits"
          description: "Mais de 10 requests/segundo sendo bloqueados por rate limit"

      # Baixa confiança média
      - alert: LowPredictionConfidence
        expr: |
          sum(rate(prediction_confidence_sum[5m])) /
          sum(rate(prediction_confidence_count[5m])) < 0.6
        for: 10m
        labels:
          severity: info
        annotations:
          summary: "Baixa confiança média"
          description: "Confiança média das predições abaixo de 60% nos últimos 10 minutos"
```

### Receivers de Notificação

```yaml
receivers:
  - name: 'slack-alerts'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        channel: '#ml-inference-alerts'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'

  - name: 'email-alerts'
    email_configs:
      - to: 'team@example.com'
        from: 'alertmanager@example.com'
        subject: '[ALERT] {{ .GroupLabels.alertname }}'
        body: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'

route:
  receiver: 'slack-alerts'
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 5m
  repeat_interval: 12h
  routes:
    - match:
        severity: critical
      receiver: 'slack-alerts'
    - match:
        severity: warning
      receiver: 'email-alerts'
```

---

## Boas Práticas

### Consultas Eficientes

1. **Usar rate() para contadores:**
   ```promql
   # Ruim
   predictions_total

   # Bom
   rate(predictions_total[5m])
   ```

2. **Evitar consultas muito amplas:**
   ```promql
   # Ruim (busca todos os dados)
   api_request_duration_seconds

   # Bom (específico)
   api_request_duration_seconds{endpoint="/api/v1/inference/predict"}
   ```

3. **Usar aggregations quando apropriado:**
   ```promql
   # Ruim (muitas séries)
   rate(predictions_total[1m])

   # Bom
   sum(rate(predictions_total[1m])) by (decision)
   ```

### Labels

- Usar labels de cardinalidade baixa
- Evitar labels com muitos valores únicos (ex: user_id)
- Labels comuns: `decision`, `endpoint`, `error_type`, `status_code`

### Retenção

Configurar retenção apropriada no Prometheus:

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

# Retenção
  retention.time: 15d
  retention.size: 10GB
```

### Performance

- Limitar número de séries temporais
- Usar recording rules para queries complexas
- Configurar scrape interval apropriado (15s padrão)

---

## Links Relacionados

- [API Documentation](./API.md)
- [Deployment Guide](./DEPLOYMENT.md)
- [Development Guide](./DEVELOPMENT.md)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
