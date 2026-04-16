# Grafana Dashboards - Fluxo G

## Overview

This directory contains Grafana dashboard definitions for monitoring Fluxo G engineering services.

## Dashboards

| Dashboard | Description | File |
|-----------|-------------|------|
| Fluxo G - Engineering Services Overview | High-level view of all services | `fluxo-g-overview.json` |
| Fluxo G - Requirements Engineering | Detailed metrics for requirements-engineering | `requirements-engineering.json` |

## Metrics

The dashboards expect the following Prometheus metrics:

### Service-Level Metrics
- `up{job="<service-name>"}` - Service health (1 = up, 0 = down)
- `http_requests_total{job="<service-name>"}` - Total HTTP requests
- `http_request_duration_seconds` - Request latency histogram

### Requirements Engineering Specific
- `requirements_generated_total` - Total requirements generated
- `user_stories_generated_total` - Total user stories created
- `acceptance_criteria_generated_total` - Total acceptance criteria created
- `requirement_generation_duration_seconds` - Time spent generating requirements

### Service Registry
- `service_registry_connections_total` - Active service registry connections

### Kafka
- `kafka_consumergroup_lag` - Consumer group lag
- `kafka_consumed_messages_total` - Messages consumed

### LLM Usage
- `llm_tokens_used_total` - Total tokens used by LLM calls

## Installation

### Method 1: Import via Grafana UI

1. Open Grafana web UI
2. Navigate to Dashboards → Import
3. Upload the JSON file from this directory

### Method 2: Use Grafana API

```bash
# Set Grafana URL and API key
GRAFANA_URL="http://localhost:3000"
GRAFANA_API_KEY="your-api-key"

# Import dashboard
curl -X POST "$GRAFANA_URL/api/dashboards/import" \
  -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @monitoring/grafana/dashboards/fluxo-g-overview.json
```

### Method 3: Auto-provision with Docker

If using the official Grafana Docker image, place dashboards in:

```
/etc/grafana/provisioning/dashboards/
```

And configure in `grafana.ini`:

```ini
[dashboards]
enabled = true
path = /etc/grafana/provisioning/dashboards
```

## Prometheus Configuration

Ensure your `prometheus.yml` includes the Fluxo G services:

```yaml
scrape_configs:
  - job_name: 'requirements-engineering'
    static_configs:
      - targets: ['requirements-engineering:8010']
    metrics_path: '/metrics'

  - job_name: 'documentation-generation'
    static_configs:
      - targets: ['documentation-generation:8014']
    metrics_path: '/metrics'

  - job_name: 'knowledge-graph-rag'
    static_configs:
      - targets: ['knowledge-graph-rag:8016']
    metrics_path: '/metrics'

  - job_name: 'approval-gateway'
    static_configs:
      - targets: ['approval-gateway:8017']
    metrics_path: '/metrics'
```

## Alerts

Recommended alert rules to configure in Prometheus Alertmanager:

```yaml
groups:
  - name: fluxo_g_alerts
    rules:
      # Service Down
      - alert: FluxoGServiceDown
        expr: up{job=~"requirements-engineering|documentation-generation|knowledge-graph-rag|approval-gateway"} == 0
        for: 1m
        annotations:
          summary: "Fluxo G service {{ $labels.job }} is down"

      # High Error Rate
      - alert: FluxoGHighErrorRate
        expr: |
          sum by (job) (rate(http_requests_total{status=~"5..", job=~"requirements-engineering|documentation-generation|knowledge-graph-rag|approval-gateway"}[5m]))
          /
          sum by (job) (rate(http_requests_total{job=~"requirements-engineering|documentation-generation|knowledge-graph-rag|approval-gateway"}[5m]))
          > 0.05
        for: 5m
        annotations:
          summary: "High error rate on {{ $labels.job }}"

      # High Latency
      - alert: FluxoGHighLatency
        expr: |
          histogram_quantile(0.95,
            sum(rate(http_request_duration_seconds_bucket{job=~"requirements-engineering|documentation-generation|knowledge-graph-rag|approval-gateway"}[5m])) by (le)
          ) > 5
        for: 5m
        annotations:
          summary: "P95 latency over 5s on {{ $labels.job }}"

      # Kafka Consumer Lag
      - alert: FluxoGKafkaConsumerLag
        expr: kafka_consumergroup_lag{job="requirements-engineering"} > 1000
        for: 10m
        annotations:
          summary: "Kafka consumer lag over 1000 messages"
```

## Variables

Dashboard variables for easy filtering:

| Variable | Values |
|----------|--------|
| `job` | requirements-engineering, documentation-generation, knowledge-graph-rag, approval-gateway |
| `namespace` | neural-hive, default |
| `instance` | Auto-discovered from Prometheus |
| `topic` | cognitive-plan, requirements, documentation, approval |

## Customization

To customize dashboards for your environment:

1. Update datasource UID from `prometheus` to your Prometheus datasource name
2. Adjust panel thresholds based on your SLA requirements
3. Add/remove panels as needed
4. Configure alert notifications (email, Slack, PagerDuty, etc.)

## Maintenance

- Update dashboards when adding new metrics
- Review and adjust alert thresholds quarterly
- Archive old dashboards instead of deleting
