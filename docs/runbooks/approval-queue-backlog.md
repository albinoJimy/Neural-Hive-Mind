# Runbook: Approval Queue Backlog

## Alerta

- **Nome**: ApprovalQueueBacklog
- **Severidade**: Warning
- **Threshold**: >50 planos pendentes por 10 minutos

## Sintomas

- Fila de aprovacoes crescendo continuamente
- Tempo de decisao aumentando
- Possivel impacto em SLAs de execucao

## Diagnostico

### 1. Verificar tamanho da fila

```bash
kubectl exec -n monitoring prometheus-0 -- promtool query instant \
  'approval_requests_pending'
```

### 2. Verificar distribuicao por risk_band

```bash
kubectl exec -n monitoring prometheus-0 -- promtool query instant \
  'approval_requests_pending' --labels
```

### 3. Checar se Approval Service esta saudavel

```bash
kubectl get pods -n neural-hive -l app=approval-service
kubectl logs -n neural-hive -l app=approval-service --tail=50
```

### 4. Verificar consumer lag do Kafka

```bash
kubectl exec -n kafka kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group approval-service-group \
  --describe
```

## Resolucao

### Acao Imediata

1. Escalar aprovadores disponiveis
2. Priorizar planos de alto risco
3. Verificar se notificacoes estao sendo enviadas

### Acao de Medio Prazo

1. Revisar criterios de bloqueio (podem estar muito restritivos)
2. Implementar auto-aprovacao para planos de baixo risco
3. Aumentar capacidade do Approval Service

### Acao de Longo Prazo

1. Implementar ML para predicao de aprovacao
2. Otimizar fluxo de geracao de planos (reduzir planos de alto risco)
3. Implementar aprovacao em lote

## Prevencao

- Monitorar tendencias de crescimento da fila
- Configurar alertas preditivos
- Revisar periodicamente criterios de risco

## Referencias

- Dashboard: https://grafana.neural-hive.io/d/approval-monitoring
- Codigo: `services/approval-service/src/services/approval_service.py`
- Documentacao: `docs/observability/approval-monitoring.md`
