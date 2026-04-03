# OPA Authorization Metrics Dashboard

## Overview

Dashboard Grafana para monitoramento completo do sistema de autorização OPA no Neural-Hive-Mind.

## Métricas Disponíveis

### Authorization Metrics
- `neural_hive_opa_authorization_total` - Total de autorizações solicitadas
- `neural_hive_opa_evaluation_results_total{result="allow|deny"}` - Resultados de avaliação
- `neural_hive_opa_evaluation_duration_seconds` - Duração da avaliação (histograma)

### Cache Metrics
- `neural_hive_opa_cache_hits_total` - Total de cache hits
- `neural_hive_opa_cache_misses_total` - Total de cache misses

### Error Metrics
- `neural_hive_opa_evaluation_errors_total{error_type}` - Erros por tipo
- `neural_hive_opa_connection_errors_total` - Erros de conexão

### Circuit Breaker Metrics
- `neural_hive_opa_circuit_breaker_state` - Estado (0=closed, 1=half_open, 2=open)
- `neural_hive_opa_circuit_breaker_failures_total` - Total de falhas

### Bundle Metrics
- `neural_hive_opa_policy_active` - Número de políticas ativas
- `neural_hive_opa_bundle_version_info` - Informações de versão (labels)

## Painéis do Dashboard

1. **Authorization Rate** - Taxa de autorizações por segundo
2. **Authorization Latency (p99)** - Latência p99 das avaliações
3. **Cache Hit Rate** - Taxa de acertos de cache
4. **Evaluation Errors** - Erros de avaliação por tipo
5. **Circuit Breaker State** - Estado atual do circuit breaker
6. **Policy Evaluation Results** - Distribuição allow/deny
7. **Active Policies** - Contador de políticas ativas
8. **Bundle Versions** - Tabela de versões de bundles

## Alertas Configurados

| Alerta | Condição | Severidade |
|--------|----------|------------|
| HighEvaluationErrorRate | >5% erros | warning |
| CircuitBreakerOpen | state=open | critical |
| HighLatency | p99 > 1s | warning |
| LowCacheHitRate | <50% hits | info |
| HighDenyRate | >30% deny | warning |
| OPADown | OPA down | critical |

## Instalação

### Via Grafana UI

1. Navegue em: + → Import
2. Cole o conteúdo de `opa-authorization-dashboard.json`
3. Configure o datasource Prometheus

### Via CLI

```bash
grafana-cli import \
  --home=http://grafana:3000 \
  /monitoring/grafana/dashboards/opa-authorization-dashboard.json
```

## Variáveis de Ambiente

- `PROMETHEUS_URL`: URL do servidor Prometheus
- `OPA_URL`: URL do servidor OPA
- `GRAFANA_API_KEY`: API key do Grafana (se autenticação habilitada)

## Troubleshooting

### Dashboard não mostra dados
- Verifique se o datasource Prometheus está configurado
- Verifique se `neural_hive_opa_*` metrics estão sendo exportadas
- Verifique se o scraping do Prometheus está ativo

### Alertas não disparam
- Verifique se Alertmanager está configurado
- Verifique se as regras estão carregadas no Alertmanager:
  ```bash
  amtool alert list
  ```
