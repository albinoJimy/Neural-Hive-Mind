# Monitoramento de Aprovacoes - Planos Cognitivos

## Visao Geral

Este documento descreve o dashboard de monitoramento de aprovacoes do Neural Hive Mind, incluindo metricas, alertas e procedimentos operacionais.

### Proposito

O dashboard `Approval Monitoring - Cognitive Plans` fornece visibilidade sobre:
- Fluxo de aprovacao de planos cognitivos
- Deteccao de operacoes destrutivas
- Cumprimento de SLAs de decisao
- Analise de risco por banda

### Publico-Alvo

- **SREs**: Monitoramento de saude do sistema
- **Admins**: Gestao de filas de aprovacao
- **Auditores**: Revisao de decisoes e compliance

## Acesso ao Dashboard

**URL**: `https://grafana.neural-hive.io/d/approval-monitoring`

### Permissoes Necessarias

- Role: `viewer` para visualizacao
- Role: `editor` para modificacoes

### Variaveis de Filtro

| Variavel | Descricao | Valores |
|----------|-----------|---------|
| `$risk_band` | Banda de risco | low, medium, high, critical |
| `$is_destructive` | Operacao destrutiva | true, false |
| `$channel` | Canal de origem | api, kafka, grpc |

## Paineis e Interpretacao

### Row 1: Overview

#### Taxa de Aprovacao (24h)

**Metrica**:
```promql
sum(rate(approvals_total{decision="approved"}[24h])) /
sum(rate(approvals_total[24h]))
```

**Interpretacao**:
- **Verde (>=70%)**: Taxa saudavel de aprovacao
- **Amarelo (50-70%)**: Taxa moderada, investigar motivos de rejeicao
- **Vermelho (<50%)**: Taxa critica, pode indicar:
  - Planos de baixa qualidade sendo gerados
  - Criterios de aprovacao muito restritivos
  - Problemas no fluxo de geracao de planos

**Acoes Recomendadas**:
1. Verificar logs de rejeicao no Approval Service
2. Analisar padroes de planos rejeitados (risk_band, is_destructive)
3. Revisar thresholds de risco em `services/semantic-translation-engine/src/config/settings.py`

#### Planos Pendentes

**Metrica**:
```promql
sum(approval_requests_pending{risk_band=~"$risk_band"})
```

**Interpretacao**:
- **Verde (<10)**: Fila saudavel
- **Amarelo (10-50)**: Fila moderada, monitorar tendencia
- **Vermelho (>50)**: Backlog critico, acionar escalonamento

#### Tempo Medio de Decisao

**Metrica**:
```promql
histogram_quantile(0.50, sum(rate(approval_time_to_decision_seconds_bucket[1h])) by (le))
```

**Interpretacao**:
- **Verde (<5min)**: Decisoes rapidas
- **Amarelo (5-30min)**: Tempo aceitavel
- **Vermelho (>30min)**: Investigar gargalos

#### Operacoes Destrutivas Bloqueadas (1h)

**Metrica**:
```promql
sum(increase(neural_hive_plans_blocked_for_approval_total{is_destructive="true"}[1h]))
```

**Interpretacao**:
- **Verde (0)**: Nenhuma operacao destrutiva
- **Amarelo (1-5)**: Operacoes destrutivas em analise
- **Vermelho (>5)**: Alta taxa de operacoes destrutivas

### Row 2: Approval Flow

#### Requests Recebidos por Banda de Risco

Visualiza a distribuicao de requests por banda de risco ao longo do tempo.

#### Decisoes por Tipo

Mostra aprovacoes vs rejeicoes por minuto.

#### Planos Pendentes por Banda de Risco

Bar gauge horizontal mostrando pendencias por banda.

### Row 3: Destructive Operations

#### Operacoes Destrutivas Detectadas

Taxa de deteccao de operacoes destrutivas por severidade.

#### Distribuicao de Tasks Destrutivas por Plano

Histograma mostrando quantas tasks destrutivas por plano.

#### Deteccoes por Tipo

Pie chart com tipos de deteccao (delete_all, drop_table, etc).

#### Top 10 Planos Destrutivos Pendentes

Tabela com planos de alto risco aguardando decisao.

### Row 4: Performance & SLAs

#### Tempo de Decisao (P50/P95/P99)

**Metricas**:
```promql
histogram_quantile(0.50, sum(rate(approval_time_to_decision_seconds_bucket[5m])) by (le))
histogram_quantile(0.95, sum(rate(approval_time_to_decision_seconds_bucket[5m])) by (le))
histogram_quantile(0.99, sum(rate(approval_time_to_decision_seconds_bucket[5m])) by (le))
```

**Linhas de Referencia**:
- Amarelo: 300s (SLO target)
- Vermelho: 1800s (SLO breach)

#### Latencia de Processamento

Heatmap de latencia de processamento de aprovacao.

#### SLA Compliance (Decisoes < 1h)

**Metrica**:
```promql
sum(rate(approval_time_to_decision_seconds_bucket{le="3600"}[24h])) /
sum(rate(approval_time_to_decision_seconds_count[24h]))
```

**Thresholds**:
- Verde: >=95% (target)
- Amarelo: 90-95%
- Vermelho: <90%

### Row 5: Risk Analysis

#### Distribuicao por Banda de Risco (24h)

Pie chart mostrando proporcao de requests por banda.

#### Taxa de Aprovacao por Banda de Risco

Taxa de aprovacao segmentada por banda de risco.

#### Historico de Decisoes (7 dias)

Time series empilhado mostrando decisoes por banda ao longo de 7 dias.

#### Risk Score - Taxa por Banda de Risco

**Metrica**:
```promql
sum by (risk_band) (rate(neural_hive_ste_risk_score_count[5m]))
```

**Interpretacao**:
- Mostra a taxa de planos processados pelo RiskScorer por banda de risco
- Permite identificar tendencias de aumento em planos de alto risco
- Util para correlacionar com picos de operacoes destrutivas

**Cores**:
- **Verde (low)**: Planos de baixo risco
- **Amarelo (medium)**: Planos de risco moderado
- **Laranja (high)**: Planos de alto risco
- **Vermelho (critical)**: Planos criticos

## Alertas e Runbooks

| Alert | Severidade | Threshold | Acao Imediata | Runbook |
|-------|------------|-----------|---------------|---------|
| ApprovalQueueBacklog | Warning | >50 pendentes por 10min | Escalar aprovadores | [Link](#runbook-approval-queue-backlog) |
| ApprovalQueueCritical | Critical | >20 alto risco por 5min | Revisar imediatamente | [Link](#runbook-approval-queue-critical) |
| ApprovalQueueStale | Warning | 0 novos em 30min + pendentes | Investigar processamento | [Link](#runbook-approval-queue-stale) |
| ApprovalPendingTooLong | Warning | Pendentes >1h | Priorizar decisoes | [Link](#runbook-approval-queue-backlog) |
| ApprovalSLABreach | Warning | P95 >1h por 15min | Investigar gargalos | [Link](#runbook-approval-sla-breach) |
| ApprovalSLACritical | Critical | P95 >2h por 10min | Escalonamento imediato | [Link](#runbook-approval-sla-breach) |
| ApprovalComplianceLow | Warning | <90% compliance por 1h | Revisar processo | [Link](#runbook-approval-sla-breach) |
| DestructiveOperationsSpike | Warning | >0.5/s por 5min | Monitorar tendencia | [Link](#runbook-destructive-spike) |
| CriticalDestructiveOperations | Critical | >0 em 10min | Revisar manualmente | [Link](#runbook-critical-destructive) |
| DestructivePlansStuck | Warning | Criticos sem decisao 1h | Priorizar decisao | [Link](#runbook-critical-destructive) |
| ApprovalServiceDown | Critical | Down por 2min | Reiniciar servico | [Link](#runbook-approval-service-down) |
| ApprovalProcessingErrors | Warning | >5% erros por 5min | Investigar logs | [Link](#runbook-approval-service-down) |
| ApprovalKafkaLag | Warning | >100 msgs por 10min | Verificar consumer | [Link](#runbook-approval-service-down) |
| HighRiskApprovalRate | Info | >30% alto risco por 30min | Monitorar tendencia | [Link](#runbook-high-risk-rate) |
| LowApprovalRate | Warning | <50% aprovacao 24h | Revisar criterios | [Link](#runbook-low-approval-rate) |

## Queries Uteis

### Listar planos pendentes ha mais de 1 hora

```promql
approval_requests_max_pending_age_seconds > 3600
```

### Taxa de aprovacao por banda de risco (ultimas 24h)

```promql
sum by (risk_band) (rate(approvals_total{decision="approved"}[24h])) /
sum by (risk_band) (rate(approvals_total[24h]))
```

### Top 5 tipos de deteccao destrutiva

```promql
topk(5,
  sum by (detection_type) (
    increase(neural_hive_destructive_operations_detected_total[24h])
  )
)
```

### Taxa de requests por canal

```promql
sum by (channel) (rate(approval_requests_received_total[1h]))
```

### Tempo medio de decisao por banda de risco

```promql
histogram_quantile(0.50,
  sum by (le, risk_band) (
    rate(approval_time_to_decision_seconds_bucket[1h])
  )
)
```

### Score de risco medio por banda (RiskScorer)

```promql
histogram_quantile(0.50,
  sum by (le, risk_band) (
    rate(neural_hive_ste_risk_score_bucket[1h])
  )
)
```

## Troubleshooting

### Cenario 1: Fila de Aprovacoes Crescendo

**Sintomas**:
- `approval_requests_pending` > 50
- Alert `ApprovalQueueBacklog` disparado

**Diagnostico**:
1. Verificar se ha aprovadores disponiveis
2. Checar se Approval Service esta processando requests
3. Validar conectividade Kafka

**Solucao**:
```bash
# Verificar pods do Approval Service
kubectl get pods -n neural-hive -l app=approval-service

# Checar logs
kubectl logs -n neural-hive -l app=approval-service --tail=100

# Verificar consumer lag
kubectl exec -n kafka kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group approval-service-group \
  --describe
```

### Cenario 2: Tempo de Decisao Alto

**Sintomas**:
- P95 de `approval_time_to_decision_seconds` > 1h
- Alert `ApprovalSLABreach` disparado

**Diagnostico**:
1. Verificar se ha planos de alto risco acumulados
2. Checar disponibilidade de aprovadores
3. Validar se notificacoes estao sendo enviadas

**Solucao**:
- Escalar equipe de aprovadores
- Revisar criterios de bloqueio (pode estar muito restritivo)
- Implementar auto-aprovacao para planos de baixo risco

### Cenario 3: Spike de Operacoes Destrutivas

**Sintomas**:
- `neural_hive_destructive_operations_detected_total` aumentando rapidamente
- Alert `DestructiveOperationsSpike` disparado

**Diagnostico**:
1. Identificar origem dos planos destrutivos
2. Verificar se e comportamento legitimo ou anomalia
3. Analisar tipos de deteccao

**Solucao**:
```bash
# Verificar ultimos planos destrutivos
kubectl logs -n neural-hive -l app=semantic-translation-engine --tail=200 | grep "destructive"

# Analisar distribuicao por tipo
curl -s 'http://prometheus:9090/api/v1/query?query=sum%20by%20(detection_type)(increase(neural_hive_destructive_operations_detected_total[1h]))'
```

### Cenario 4: Approval Service Down

**Sintomas**:
- Alert `ApprovalServiceDown` disparado
- Fila de aprovacoes crescendo

**Diagnostico**:
1. Verificar status dos pods
2. Checar logs de erro
3. Validar conectividade com dependencias

**Solucao**:
```bash
# Verificar pods
kubectl get pods -n neural-hive -l app=approval-service

# Descrever pod com problema
kubectl describe pod -n neural-hive <pod-name>

# Reiniciar deployment
kubectl rollout restart deployment/approval-service -n neural-hive
```

## Manutencao do Dashboard

### Adicionar Novos Paineis

1. Editar `monitoring/dashboards/approval-monitoring.json`
2. Adicionar painel seguindo estrutura existente
3. Aplicar ConfigMap: `kubectl apply -f monitoring/dashboards/`

### Ajustar Thresholds

1. Identificar painel no JSON
2. Modificar `thresholds.steps`
3. Aplicar mudancas

### Exportar/Importar Dashboard

```bash
# Exportar
curl -s 'http://grafana:3000/api/dashboards/uid/approval-monitoring' > backup.json

# Importar
curl -X POST -H "Content-Type: application/json" \
  -d @backup.json \
  'http://grafana:3000/api/dashboards/db'
```

## Referencias

### Codigo-Fonte

- Metricas Prometheus: `services/approval-service/src/observability/metrics.py`
- DestructiveDetector: `services/semantic-translation-engine/src/services/destructive_detector.py`
- RiskScorer: `services/semantic-translation-engine/src/services/risk_scorer.py`
- Configuracao: `services/semantic-translation-engine/src/config/settings.py`

### Documentacao Externa

- [Grafana Documentation](https://grafana.com/docs/)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [PromQL Cheat Sheet](https://promlabs.com/promql-cheat-sheet/)
