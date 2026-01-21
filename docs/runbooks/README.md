# Runbooks Index

Este diretorio contem runbooks operacionais para o Neural Hive Mind. Cada runbook fornece instrucoes detalhadas para diagnostico e resolucao de problemas especificos.

## Estrutura dos Runbooks

Cada runbook segue uma estrutura padronizada:

1. **Alerta** - Nome dos alertas relacionados, severidade e thresholds
2. **Sintomas** - Como identificar o problema
3. **Diagnostico** - Comandos e verificacoes para entender a causa raiz
4. **Resolucao** - Opcoes de resolucao ordenadas por prioridade
5. **Verificacao de Recuperacao** - Como confirmar que o problema foi resolvido
6. **Prevencao** - Acoes para evitar recorrencia
7. **Referencias** - Links para dashboards, codigo e documentacao relacionada

---

## ML Models & Predictions

Runbooks relacionados a modelos de Machine Learning, predicoes e performance.

| Runbook | Alertas Relacionados | Severidade |
|---------|---------------------|------------|
| [ml-drift-critical.md](./ml-drift-critical.md) | MLDriftCritical, MLDriftWarning, MLFeatureDriftHigh, MLPredictionDriftCritical, MLTargetDriftDetected | Critical/Warning |
| [model-degraded.md](./model-degraded.md) | MLModelDegraded, MLModelLowPerformance, MLModelLowF1Score | Warning |
| [auto-retrain-failed.md](./auto-retrain-failed.md) | AutoRetrainFailed, AutoRetrainLongDuration, NoRetrainWithDrift | Warning |
| [feedback-collection-low.md](./feedback-collection-low.md) | MLModelFeedbackRateSLOBreach, MLModelFeedbackRateSLOCritical | Warning/Critical |

---

## Approval Service

Runbooks relacionados ao servico de aprovacao e filas.

| Runbook | Alertas Relacionados | Severidade |
|---------|---------------------|------------|
| [approval-service-down.md](./approval-service-down.md) | ApprovalServiceDown | Critical |
| [approval-queue-backlog.md](./approval-queue-backlog.md) | ApprovalQueueBacklog | Warning |
| [approval-sla-breach.md](./approval-sla-breach.md) | ApprovalSLABreach | Warning |

---

## Security & Destructive Operations

Runbooks relacionados a seguranca e operacoes destrutivas.

| Runbook | Alertas Relacionados | Severidade |
|---------|---------------------|------------|
| [critical-destructive.md](./critical-destructive.md) | CriticalDestructiveOperation | Critical |
| [destructive-spike.md](./destructive-spike.md) | DestructiveOperationSpike | Warning |

---

## Worker Agents

Runbooks relacionados aos agentes de trabalho.

| Runbook | Alertas Relacionados | Severidade |
|---------|---------------------|------------|
| [worker-agents-troubleshooting.md](./worker-agents-troubleshooting.md) | WorkerAgentUnhealthy | Warning |
| [worker-agents-rollback.md](./worker-agents-rollback.md) | WorkerAgentRollback | Warning |

---

## Infrastructure & Storage

Runbooks relacionados a infraestrutura e armazenamento.

| Runbook | Alertas Relacionados | Severidade |
|---------|---------------------|------------|
| [code-forge-s3-sbom-storage.md](./code-forge-s3-sbom-storage.md) | S3StorageIssue, SBOMStorageFailure | Warning |

---

## Phase 2 Operations

Runbooks gerais para operacoes da Fase 2.

| Runbook | Descricao |
|---------|-----------|
| [phase2-operations.md](./phase2-operations.md) | Guia geral de operacoes da Fase 2 |
| [phase2-troubleshooting-flowchart.md](./phase2-troubleshooting-flowchart.md) | Fluxograma de troubleshooting |
| [phase2-disaster-recovery.md](./phase2-disaster-recovery.md) | Procedimentos de disaster recovery |

---

## Alert Management

Para informacoes sobre como gerenciar alertas ML (silenciar, escalar, resolver), consulte:
- [Alert Management Guide](../operations/alert-management.md)

### Comandos Rapidos de Alerting

```bash
# Silenciar alerta durante manutencao
kubectl exec -n monitoring alertmanager-0 -- amtool silence add \
  alertname="MLDriftCritical" --duration=2h --comment="Manutencao" --author="$(whoami)"

# Verificar alertas ativos
kubectl exec -n monitoring alertmanager-0 -- amtool alert query

# Testar routing de alerta
kubectl exec -n monitoring alertmanager-0 -- amtool config routes test \
  alertname="MLDriftCritical" severity="critical"

# Listar silences ativos
kubectl exec -n monitoring alertmanager-0 -- amtool silence query
```

---

## Quick Reference

### Comandos Uteis

```bash
# Ver logs do orchestrator
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=100

# Ver status dos pods
kubectl get pods -n neural-hive-orchestration

# Acessar MongoDB
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python -c "from pymongo import MongoClient; print(MongoClient('mongodb://mongodb.neural-hive:27017').server_info())"

# Verificar alertas ativos
curl -s http://alertmanager.monitoring:9093/api/v2/alerts | jq '.[] | select(.status.state == "active") | {alertname: .labels.alertname, severity: .labels.severity}'

# Verificar metricas Prometheus
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=up" | jq '.data.result'
```

### Dashboards

| Dashboard | URL |
|-----------|-----|
| ML Predictions | https://grafana.neural-hive.local/d/orchestrator-ml-predictions |
| ML SLOs | https://grafana.neural-hive.local/d/ml-slos-dashboard/ml-slos |
| SLOs & Error Budgets | https://grafana.neural-hive.local/d/slos-error-budgets |
| Approval Service | https://grafana.neural-hive.local/d/approval-service |

### Contatos

| Equipe | Canal |
|--------|-------|
| ML Platform | #ml-platform-oncall |
| SRE | #sre-oncall |
| Produto | #product-support |

---

## Contribuindo

Para adicionar um novo runbook:

1. Crie o arquivo seguindo a estrutura padrao
2. Use o template em `/docs/templates/runbook-template.md` (se disponivel)
3. Adicione entrada neste README na secao apropriada
4. Atualize os alertas Prometheus com a URL do novo runbook
5. Teste os comandos de diagnostico antes de fazer merge

## Versionamento

Os runbooks sao versionados junto com o codigo. Ao modificar alertas ou procedimentos:

1. Atualize o runbook correspondente
2. Atualize as URLs nos alertas Prometheus se necessario
3. Notifique a equipe de oncall sobre mudancas significativas
