# Guia de Sincronização de CRDs SLO

Este guia descreve o sistema de sincronização entre CRDs `SLODefinition` do Kubernetes e o banco de dados PostgreSQL.

## Visão Geral

O sistema utiliza duas abordagens complementares para sincronização:

| Componente | Tipo | Frequência | Propósito |
|------------|------|------------|-----------|
| **Operator** | Tempo real | Eventos | Sincronização imediata via handlers kopf |
| **CronJob** | Periódico | 15 minutos | Reconciliação e recuperação de drift |

## Arquitetura

```
┌─────────────────┐     ┌──────────────────┐     ┌────────────────┐
│  CRD            │────▶│  Operator (kopf) │────▶│  PostgreSQL    │
│  SLODefinition  │     │  (tempo real)    │     │                │
└─────────────────┘     └──────────────────┘     └────────────────┘
        │                                               ▲
        │               ┌──────────────────┐            │
        └──────────────▶│  CronJob (15min) │────────────┘
                        │  (reconciliação) │
                        └──────────────────┘
```

## Como Aplicar CRDs

### 1. Criar SLODefinition

```bash
# Aplicar exemplo de SLO de latência
kubectl apply -f examples/slo-latency-example.yaml

# Verificar criação
kubectl get slo -n neural-hive
```

### 2. Exemplo de CRD Completo

```yaml
apiVersion: neural-hive.io/v1
kind: SLODefinition
metadata:
  name: gateway-latency-p99
  namespace: neural-hive
spec:
  name: "Gateway P99 Latency"
  description: "99th percentile latency for gateway"
  sloType: LATENCY
  serviceName: gateway-intencoes
  layer: experiencia
  target: 0.999
  windowDays: 30
  sliQuery:
    metricName: http_request_duration_seconds
    query: |
      histogram_quantile(0.99,
        sum(rate(http_request_duration_seconds_bucket{service="gateway-intencoes"}[5m])) by (le)
      )
    aggregation: avg
  enabled: true
```

## Verificar Sincronização

### Status do CRD

```bash
# Ver status de sincronização
kubectl get slo gateway-latency-p99 -n neural-hive -o yaml

# Campos de status importantes:
# - status.synced: true/false
# - status.lastSyncTime: timestamp da última sincronização
# - status.sloId: UUID gerado no PostgreSQL
```

### Listar Todos os SLOs

```bash
# Listar com colunas adicionais
kubectl get slo -n neural-hive -o wide

# Saída esperada:
# NAME                  TYPE      TARGET   BUDGET   STATUS    SYNCED   AGE
# gateway-latency-p99   LATENCY   0.999    85.2%    HEALTHY   true     2d
```

## Troubleshooting

### Logs do CronJob

```bash
# Ver jobs recentes
kubectl get jobs -n neural-hive -l app.kubernetes.io/name=slo-crd-sync-job

# Logs do último job
kubectl logs -n neural-hive -l app.kubernetes.io/name=slo-crd-sync-job --tail=100
```

### Logs do Operator

```bash
# Logs do operator
kubectl logs -n neural-hive -l app.kubernetes.io/name=sla-management-operator --tail=100
```

### SLO não sincronizado

1. Verificar se CRD foi aplicado corretamente:
   ```bash
   kubectl describe slo <nome> -n <namespace>
   ```

2. Verificar eventos:
   ```bash
   kubectl get events -n neural-hive --field-selector reason=SyncFailed
   ```

3. Verificar conectividade com PostgreSQL:
   ```bash
   kubectl exec -n neural-hive deploy/sla-management-system -- \
     python -c "from src.clients.postgresql_client import PostgreSQLClient; print('OK')"
   ```

## Comandos Úteis

```bash
# Descrever SLO específico
kubectl describe slo gateway-latency-p99 -n neural-hive

# Editar SLO
kubectl edit slo gateway-latency-p99 -n neural-hive

# Deletar SLO
kubectl delete slo gateway-latency-p99 -n neural-hive

# Forçar sincronização manual
kubectl create job --from=cronjob/slo-crd-sync manual-sync-$(date +%s) -n neural-hive

# Ver histórico de jobs
kubectl get jobs -n neural-hive -l app.kubernetes.io/name=slo-crd-sync-job --sort-by=.metadata.creationTimestamp
```

## Configuração

### Variáveis de Ambiente do CronJob

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `POSTGRESQL__HOST` | Host do PostgreSQL | `postgres-sla.neural-hive-data.svc.cluster.local` |
| `KUBERNETES__IN_CLUSTER` | Executando dentro do cluster | `true` |
| `KUBERNETES__NAMESPACE` | Namespace padrão | `neural-hive` |
| `LOG_LEVEL` | Nível de log | `INFO` |

### RBAC Necessário

O CronJob requer as seguintes permissões:

- `get`, `list`, `watch` em `slodefinitions`
- `get`, `update`, `patch` em `slodefinitions/status`

Aplicar RBAC:
```bash
kubectl apply -f k8s/rbac/sla-management-crd-sync-rbac.yaml
```
