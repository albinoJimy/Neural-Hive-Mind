# Runbook: Approval SLA Breach

## Alerta

- **Nome**: ApprovalSLABreach / ApprovalSLACritical
- **Severidade**: Warning / Critical
- **Threshold**: P95 >1h (Warning) / P95 >2h (Critical)

## Sintomas

- Tempo de decisao de aprovacao acima do SLO
- Planos aguardando decisao por muito tempo
- Compliance SLA abaixo de 95%

## Diagnostico

### 1. Verificar percentis de tempo de decisao

```bash
kubectl exec -n monitoring prometheus-0 -- promtool query instant \
  'histogram_quantile(0.95, sum(rate(approval_time_to_decision_seconds_bucket[1h])) by (le))'
```

### 2. Identificar planos mais antigos pendentes

```bash
kubectl exec -n monitoring prometheus-0 -- promtool query instant \
  'approval_requests_pending{risk_band=~"high|critical"}'
```

### 3. Verificar compliance atual

```bash
kubectl exec -n monitoring prometheus-0 -- promtool query instant \
  'sum(rate(approval_time_to_decision_seconds_bucket{le="3600"}[24h])) / sum(rate(approval_time_to_decision_seconds_count[24h]))'
```

### 4. Analisar distribuicao por banda de risco

```bash
kubectl exec -n monitoring prometheus-0 -- promtool query instant \
  'histogram_quantile(0.95, sum by (le, risk_band) (rate(approval_time_to_decision_seconds_bucket[1h])))'
```

## Resolucao

### Acao Imediata

1. Identificar planos pendentes ha mais tempo
2. Escalar equipe de aprovadores
3. Priorizar decisoes em planos de alto risco

### Acao de Medio Prazo

1. Revisar processo de aprovacao para gargalos
2. Implementar notificacoes mais agressivas para aprovadores
3. Considerar auto-aprovacao para planos de baixo risco

### Acao de Longo Prazo

1. Implementar aprovacao por regras automaticas
2. Adicionar SLAs diferenciados por banda de risco
3. Criar dashboards de accountability para aprovadores

## Metricas de Recuperacao

- P95 tempo de decisao < 1h
- Compliance SLA >= 95%
- Zero planos pendentes ha mais de 2h

## Referencias

- Dashboard: https://grafana.neural-hive.io/d/approval-monitoring
- Codigo: `services/approval-service/src/services/approval_service.py`
- Configuracao SLA: `services/approval-service/src/config/settings.py`
