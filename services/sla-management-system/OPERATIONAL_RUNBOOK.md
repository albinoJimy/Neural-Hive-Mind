# Operational Runbook - SLA Management System

## Referência Rápida

### Contatos de Emergência
- **Time SRE**: #neural-hive-sre (Slack)
- **On-Call**: PagerDuty - Neural Hive Critical
- **Escalação**: SRE Lead → Engineering Manager → CTO

### Comandos Essenciais

```bash
# Status do sistema
kubectl get pods -n neural-hive-monitoring -l app.kubernetes.io/name=sla-management-system

# Logs
kubectl logs -n neural-hive-monitoring -l app.kubernetes.io/name=sla-management-system -f

# Health check
kubectl port-forward -n neural-hive-monitoring svc/sla-management-system 8000:8000
curl http://localhost:8000/health

# Listar SLOs
kubectl get slodefinitions --all-namespaces

# Listar políticas
kubectl get slapolicies --all-namespaces

# Listar freezes ativos
curl http://sla-management-system.neural-hive-monitoring.svc.cluster.local:8000/api/v1/policies/freezes/active
```

### URLs Importantes
- **API**: http://sla-management-system.neural-hive-monitoring.svc.cluster.local:8000
- **Métricas**: http://sla-management-system.neural-hive-monitoring.svc.cluster.local:9090/metrics
- **Dashboard**: https://grafana.neural-hive.io/d/sla-management-system
- **Docs**: /docs (API OpenAPI)

## Tarefas Operacionais Comuns

### Verificar Saúde do Sistema

```bash
# 1. Verificar pods
kubectl get pods -n neural-hive-monitoring -l app.kubernetes.io/name=sla-management-system

# 2. Health endpoint
curl http://localhost:8000/health

# 3. Ready endpoint
curl http://localhost:8000/ready | jq

# Resposta esperada:
# {
#   "ready": true,
#   "postgresql": "ok",
#   "redis": "ok",
#   "prometheus": "ok",
#   "kafka": "ok"
# }
```

**O que fazer se unhealthy**:
1. Verificar logs para erros
2. Verificar conectividade com dependências (PostgreSQL, Redis, Prometheus)
3. Verificar recursos (CPU, memória)
4. Reiniciar pod se necessário

### Ver SLOs e Budgets Atuais

```bash
# Listar todos os SLOs
kubectl get slodefinitions --all-namespaces

# Ver detalhes de um SLO específico
kubectl get slodefinition <name> -n <namespace> -o yaml

# Ver budget via API
curl http://localhost:8000/api/v1/budgets/<slo_id> | jq
```

**Interpretando o budget**:
- `remaining_percent > 50`: HEALTHY (verde)
- `20 < remaining_percent <= 50`: WARNING (amarelo)
- `0 < remaining_percent <= 20`: CRITICAL (laranja)
- `remaining_percent <= 0`: EXHAUSTED (vermelho)

### Criar Novo SLO

**Via CRD (Recomendado)**:
```bash
cat <<EOF | kubectl apply -f -
apiVersion: neural-hive.io/v1
kind: SLODefinition
metadata:
  name: my-service-latency
  namespace: my-namespace
spec:
  name: "My Service - Latency SLO"
  sloType: LATENCY
  serviceName: my-service
  layer: application
  target: 0.99
  windowDays: 30
  sliQuery:
    metricName: my_metric
    query: "histogram_quantile(0.95, rate(my_metric_bucket[5m])) < 0.2"
  enabled: true
EOF
```

**Validação**:
```bash
# Aguardar 10s e verificar status
kubectl get slodefinition my-service-latency -n my-namespace -o jsonpath='{.status.synced}'
# Deve retornar: true
```

### Gerenciar Freeze Events

#### Ver Freezes Ativos

```bash
# Via API
curl http://localhost:8000/api/v1/policies/freezes/active | jq

# Via kubectl (verificar annotations)
kubectl get deployments -A -o json | jq '.items[] | select(.metadata.annotations["neural-hive.io/freeze"] == "true") | {namespace: .metadata.namespace, name: .metadata.name}'
```

#### Resolver Freeze Manualmente

```bash
# 1. Identificar freeze event ID
FREEZE_ID=$(curl http://localhost:8000/api/v1/policies/freezes/active | jq -r '.[0].id')

# 2. Resolver
curl -X POST http://localhost:8000/api/v1/policies/freezes/$FREEZE_ID/resolve
```

**Quando resolver manualmente**:
- Budget foi restaurado mas auto-unfreeze falhou
- Freeze foi ativado por engano
- Urgência de deployment crítico (com aprovação de SRE Lead)

#### Desabilitar Política Temporariamente

```bash
kubectl patch slapolicy <policy-name> -n <namespace> --type merge -p '{"spec":{"enabled":false}}'

# Reabilitar depois
kubectl patch slapolicy <policy-name> -n <namespace> --type merge -p '{"spec":{"enabled":true}}'
```

### Investigar Alto Burn Rate

**Sintoma**: Alert "HighBurnRateFast" ou "HighBurnRateSlow"

**Passos**:

1. **Identificar SLO afetado**:
```bash
# Ver alertas ativos
curl http://alertmanager.monitoring.svc.cluster.local:9093/api/v2/alerts | jq '.[] | select(.labels.alertname | contains("BurnRate"))'
```

2. **Verificar budget**:
```bash
SLO_ID=<id-do-alerta>
curl http://localhost:8000/api/v1/budgets/$SLO_ID | jq
```

3. **Analisar métricas no Prometheus**:
```bash
# Query de exemplo
curl 'http://prometheus-server.monitoring.svc.cluster.local:9090/api/v1/query?query=sla_burn_rate{slo_id="<slo_id>"}'
```

4. **Correlacionar com eventos**:
- Deployments recentes?
- Incidentes em andamento?
- Mudanças de tráfego?

5. **Ações**:
- Se incidente: Resolver incidente primeiro
- Se deployment ruim: Rollback
- Se tráfego anormal: Investigar causa

### Ajustar SLO Target

**Quando ajustar**:
- SLO muito apertado (budget sempre crítico)
- SLO muito frouxo (budget nunca consumido)
- Mudança de requisitos de negócio

**Como ajustar**:
```bash
kubectl patch slodefinition <name> -n <namespace> --type merge -p '{"spec":{"target":0.995}}'
```

**Recomendações**:
- Availability: 99% (0.99) a 99.99% (0.9999)
- Latency: 95% (0.95) a 99.9% (0.999)
- Error Rate: 98% (0.98) a 99.9% (0.999)

### Escalar o Sistema

**Manual**:
```bash
# API Server
kubectl scale deployment sla-management-system -n neural-hive-monitoring --replicas=4

# Verificar HPA atual
kubectl get hpa sla-management-system -n neural-hive-monitoring
```

**Ajustar HPA**:
```bash
kubectl patch hpa sla-management-system -n neural-hive-monitoring --type merge -p '{"spec":{"maxReplicas":10}}'
```

**Quando escalar**:
- Alta carga de cálculos (muitos SLOs)
- Slow queries no Prometheus
- High CPU/Memory usage

## Procedimentos de Incidentes

### INCIDENTE: Sistema Completamente Down

**Detecção**: Alert "SLAManagementSystemDown"

**Impacto**:
- Sem cálculo de budgets
- Sem enforcement de freeze policies
- SLOs não monitorados

**Ações Imediatas**:

1. **Verificar pods**:
```bash
kubectl get pods -n neural-hive-monitoring -l app.kubernetes.io/name=sla-management-system
```

2. **Ver logs**:
```bash
kubectl logs -n neural-hive-monitoring -l app.kubernetes.io/name=sla-management-system --tail=200
```

3. **Verificar eventos**:
```bash
kubectl get events -n neural-hive-monitoring --sort-by='.lastTimestamp' | grep sla-management
```

4. **Causas comuns e soluções**:

**a) ImagePullBackOff**:
```bash
# Verificar imagem
kubectl describe pod <pod-name> -n neural-hive-monitoring | grep Image

# Solução: Atualizar tag ou registry
helm upgrade sla-management-system ./helm-charts/sla-management-system \
  --set image.tag=<correct-tag> \
  --namespace neural-hive-monitoring
```

**b) CrashLoopBackOff**:
```bash
# Ver último erro
kubectl logs <pod-name> -n neural-hive-monitoring --previous

# Causas comuns:
# - PostgreSQL indisponível: Verificar postgres-sla pod
# - Secret incorreto: Verificar sla-management-system-secret
# - OOM: Aumentar memory limits
```

**c) Recursos insuficientes**:
```bash
kubectl describe nodes | grep -A 5 "Allocated resources"

# Solução: Adicionar nodes ou reduzir outras cargas
```

5. **Restart de emergência**:
```bash
kubectl rollout restart deployment/sla-management-system -n neural-hive-monitoring
```

**Escalação**: Se não resolver em 15 minutos, page SRE Lead.

### INCIDENTE: Múltiplos Budgets Críticos

**Detecção**: Alert "MultipleCriticalBudgets"

**Impacto**: Múltiplos serviços em risco de violar SLO

**Ações**:

1. **Identificar serviços afetados**:
```bash
curl http://localhost:8000/api/v1/slos | jq '.[] | select(.current_budget.status == "CRITICAL" or .current_budget.status == "EXHAUSTED") | {name, service_name, budget_remaining: .current_budget.remaining_percent}'
```

2. **Verificar causa comum**:
```bash
# Cluster-wide issue?
kubectl top nodes
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -50

# Prometheus issues?
kubectl get pods -n monitoring -l app=prometheus
```

3. **Comunicação**:
```bash
# Notificar stakeholders
# Template:
# "ALERTA: Múltiplos SLOs em estado crítico
#  Serviços afetados: [lista]
#  Budget restante: [valores]
#  Ação: Investigando causa raiz
#  ETA: [tempo estimado]"
```

4. **Mitigação**:
- Se incidente cluster-wide: Resolver infra issue
- Se deployments ruins: Coordenar rollbacks
- Se sobrecarga: Aplicar rate limiting, scale out

**Decisão de Freeze**:
- Budget < 10%: Considerar freeze global
- Budget < 20%: Freeze por namespace/service
- Requere aprovação de Engineering Manager

### INCIDENTE: Operator Não Sincroniza

**Detecção**: Alert "CRDSyncFailures" ou `status.synced: false`

**Ações**:

1. **Ver logs do operator**:
```bash
kubectl logs -n neural-hive-monitoring -l app.kubernetes.io/component=operator --tail=100
```

2. **Verificar RBAC**:
```bash
# Testar permissions
kubectl auth can-i get slodefinitions --as=system:serviceaccount:neural-hive-monitoring:sla-management-system-operator

# Deve retornar: yes
```

3. **Verificar CRD status**:
```bash
kubectl get slodefinition <name> -n <namespace> -o jsonpath='{.status.conditions}'
```

4. **Forçar reconciliação**:
```bash
# Adicionar annotation para trigger
kubectl annotate slodefinition <name> -n <namespace> neural-hive.io/force-sync="$(date +%s)"
```

5. **Restart operator**:
```bash
kubectl rollout restart deployment/sla-management-system-operator -n neural-hive-monitoring
```

### INCIDENTE: Budget Não Atualiza

**Sintoma**: `last_calculated_at` não muda há > 5 minutos

**Ações**:

1. **Verificar intervalo de cálculo**:
```bash
kubectl get configmap sla-management-system-config -n neural-hive-monitoring -o jsonpath='{.data.calculator_interval_seconds}'
# Default: 30
```

2. **Verificar Prometheus connectivity**:
```bash
kubectl run curl-test --image=curlimages/curl --rm -it --restart=Never -- \
  curl http://prometheus-server.monitoring.svc.cluster.local:9090/api/v1/status/config
```

3. **Testar query SLI**:
```bash
# Pegar query do SLO
QUERY=$(kubectl get slodefinition <name> -n <namespace> -o jsonpath='{.spec.sliQuery.query}')

# Testar no Prometheus
curl -G 'http://prometheus-server.monitoring.svc.cluster.local:9090/api/v1/query' \
  --data-urlencode "query=$QUERY"
```

4. **Verificar métricas de cálculo**:
```bash
kubectl port-forward -n neural-hive-monitoring svc/sla-management-system 9090:9090
curl http://localhost:9090/metrics | grep sla_calculations_total
```

5. **Forçar recálculo**:
```bash
curl -X POST http://localhost:8000/api/v1/budgets/<slo_id>/recalculate
```

## Manutenção

### Backup de CRDs

**Frequência**: Diário (automatizado via CronJob recomendado)

```bash
#!/bin/bash
DATE=$(date +%Y%m%d)
kubectl get slodefinitions --all-namespaces -o yaml > slos-backup-$DATE.yaml
kubectl get slapolicies --all-namespaces -o yaml > policies-backup-$DATE.yaml

# Upload para S3
aws s3 cp slos-backup-$DATE.yaml s3://neural-hive-backups/sla-crds/
aws s3 cp policies-backup-$DATE.yaml s3://neural-hive-backups/sla-crds/
```

### Limpeza de Dados Antigos

**PostgreSQL**:
```sql
-- Deletar budgets com mais de 90 dias
DELETE FROM error_budgets WHERE calculated_at < NOW() - INTERVAL '90 days';

-- Vacuum
VACUUM ANALYZE error_budgets;
```

### Upgrade do Sistema

Ver [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md#upgrade)

## Debugging

### Logs Lentos de Cálculo

**Sintoma**: `sla_calculation_duration_seconds` > 10s

**Investigação**:
```bash
# Ver queries lentas
kubectl logs -n neural-hive-monitoring -l app.kubernetes.io/name=sla-management-system | grep "slow_query"

# Verificar Prometheus query performance
curl -G 'http://prometheus-server.monitoring.svc.cluster.local:9090/api/v1/query' \
  --data-urlencode "query=<slow-query>" \
  --data-urlencode "stats=all"
```

**Soluções**:
- Simplificar query PromQL
- Adicionar índices no Prometheus
- Aumentar `prometheus.timeoutSeconds`
- Reduzir `windowDays` do SLO

### Budget Valor Incorreto

**Verificação**:
```bash
# 1. Testar SLI query manualmente
curl -G 'http://prometheus-server.monitoring.svc.cluster.local:9090/api/v1/query' \
  --data-urlencode "query=<sli-query>"

# 2. Comparar com valor calculado
curl http://localhost:8000/api/v1/budgets/<slo_id> | jq '.current_sli'

# 3. Ver cálculo detalhado (logs)
kubectl logs -n neural-hive-monitoring -l app.kubernetes.io/name=sla-management-system | grep "slo_id=<slo_id>"
```

**Causas comuns**:
- Query PromQL incorreta
- Dados faltando no Prometheus
- Lógica de agregação errada
- Window incorreto

## Performance Tuning

### Reduzir Latência de Cálculo

```yaml
# values.yaml
config:
  calculator:
    calculationIntervalSeconds: 60  # De 30 para 60
  postgresql:
    poolMaxSize: 20  # De 10 para 20
  prometheus:
    timeoutSeconds: 60  # De 30 para 60
```

### Reduzir Uso de Memória

```yaml
resources:
  limits:
    memory: 1Gi  # De 2Gi para 1Gi (se possível)

config:
  redis:
    cacheTtlSeconds: 30  # De 60 para 30
```

### Escalar Horizontalmente

```yaml
autoscaling:
  minReplicas: 3  # De 2 para 3
  maxReplicas: 10  # De 6 para 10
  targetCPUUtilizationPercentage: 60  # De 70 para 60
```

## Métricas-Chave para Monitorar

| Métrica | Threshold | Ação |
|---------|-----------|------|
| `sla_calculations_total{status="error"}` | > 5% | Investigar erros |
| `sla_calculation_duration_seconds` P95 | > 10s | Otimizar queries |
| `sla_budget_status{status="EXHAUSTED"}` | > 0 | Incidente crítico |
| `sla_freezes_active` | > 5 | Revisar políticas |
| `sla_postgresql_connection_errors_total` | > 0 | Verificar PostgreSQL |
| `up{job="sla-management-system"}` | < 1 | Sistema down |

## Contatos e Referências

### Time
- **SRE Team**: @sre-team (Slack #neural-hive-sre)
- **Development**: @neural-hive-dev (Slack #neural-hive-dev)
- **On-Call**: PagerDuty rotation

### Documentação
- [README](README.md)
- [Deployment Guide](DEPLOYMENT_GUIDE.md)
- [Implementation Notes](IMPLEMENTATION_NOTES.md)
- [API Docs](http://sla-management-system.neural-hive-monitoring.svc.cluster.local:8000/docs)

### Ferramentas
- **Grafana**: https://grafana.neural-hive.io
- **Prometheus**: https://prometheus.neural-hive.io
- **Alertmanager**: https://alertmanager.neural-hive.io
