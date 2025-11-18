# Guia de Deployment - SLA Management System

## Visão Geral

Este guia fornece instruções completas para deployment do SLA Management System no cluster Kubernetes do Neural Hive-Mind.

### Componentes Principais

- **API Server**: API REST para gerenciamento de SLOs, budgets e políticas
- **Kubernetes Operator**: Reconciliação de CRDs (SLODefinition, SLAPolicy)
- **Budget Calculator**: Cálculo contínuo de error budgets
- **Policy Enforcer**: Aplicação de freeze policies baseadas em thresholds

## Pré-requisitos

### Infraestrutura Necessária

| Componente | Versão Mínima | Namespace | Descrição |
|------------|---------------|-----------|-----------|
| Kubernetes | 1.24+ | - | Cluster Kubernetes |
| Helm | 3.8+ | - | Gerenciador de pacotes |
| PostgreSQL | 13+ | neural-hive-data | Persistência de dados |
| Redis | 6.2+ | redis-cluster | Cache de budgets |
| Kafka | 3.0+ | kafka | Event streaming |
| Prometheus | 2.40+ | monitoring | Queries de métricas |
| Alertmanager | 0.24+ | monitoring | Webhook de alertas |

### Recursos Necessários

**Por Pod (API Server)**:
- CPU: 200m (request) / 1000m (limit)
- Memory: 512Mi (request) / 2Gi (limit)

**Por Pod (Operator)**:
- CPU: 100m (request) / 500m (limit)
- Memory: 256Mi (request) / 1Gi (limit)

**Total para HA (2 API + 1 Operator)**:
- CPU: ~600m request / 2500m limit
- Memory: ~1.3Gi request / 5Gi limit

### Permissões RBAC

- **Cluster-wide**: Acesso a CRDs, namespaces, deployments, statefulsets
- **Namespace-scoped**: Acesso a ConfigMaps, Secrets, Events

## Instalação

### Opção 1: Script Automatizado (Recomendado)

```bash
# Instalação completa
./scripts/deploy/deploy-sla-management-system.sh

# Com valores customizados
./scripts/deploy/deploy-sla-management-system.sh --values my-values.yaml

# Dry-run para validar
./scripts/deploy/deploy-sla-management-system.sh --dry-run

# Namespace customizado
./scripts/deploy/deploy-sla-management-system.sh --namespace my-namespace
```

### Opção 2: Manual

#### Passo 1: Instalar CRDs

```bash
kubectl apply -f k8s/crds/slodefinition-crd.yaml
kubectl apply -f k8s/crds/slapolicy-crd.yaml

# Verificar estabelecimento
kubectl wait --for condition=established --timeout=60s crd/slodefinitions.neural-hive.io
kubectl wait --for condition=established --timeout=60s crd/slapolicies.neural-hive.io
```

#### Passo 2: Criar Tópicos Kafka

```bash
kubectl apply -f k8s/kafka-topics/sla-topics.yaml

# Verificar criação
kubectl get kafkatopic -n kafka | grep sla
```

#### Passo 3: Configurar Secrets

```bash
# IMPORTANTE: Use SealedSecrets em produção
kubectl create secret generic sla-management-system-secret \
  --namespace neural-hive-monitoring \
  --from-literal=POSTGRESQL__USER=sla_user \
  --from-literal=POSTGRESQL__PASSWORD='<secure-password>' \
  --from-literal=REDIS__PASSWORD='<secure-password>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

#### Passo 4: Instalar Helm Chart

```bash
helm upgrade --install sla-management-system \
  ./helm-charts/sla-management-system \
  --namespace neural-hive-monitoring \
  --create-namespace \
  --values helm-charts/sla-management-system/values.yaml \
  --wait \
  --timeout 10m
```

#### Passo 5: Verificar Deployment

```bash
# Verificar pods
kubectl get pods -n neural-hive-monitoring -l app.kubernetes.io/name=sla-management-system

# Verificar rollout
kubectl rollout status deployment/sla-management-system -n neural-hive-monitoring

# Verificar operator (se habilitado)
kubectl rollout status deployment/sla-management-system-operator -n neural-hive-monitoring
```

## Configuração

### Variáveis de Ambiente Principais

```yaml
# values.yaml
config:
  # Prometheus
  prometheus:
    url: http://prometheus-server.monitoring.svc.cluster.local:9090
    timeoutSeconds: 30

  # PostgreSQL
  postgresql:
    host: postgres-sla.neural-hive-data.svc.cluster.local
    port: 5432
    database: sla_management
    poolMaxSize: 10

  # Redis
  redis:
    clusterNodes: redis-cluster.redis-cluster.svc.cluster.local:6379
    cacheTtlSeconds: 60

  # Kafka
  kafka:
    bootstrapServers: kafka-bootstrap.kafka.svc.cluster.local:9092
    budgetTopic: sla.budgets
    freezeTopic: sla.freeze.events

  # Budget Calculator
  calculator:
    calculationIntervalSeconds: 30
    burnRateFastThreshold: 14.4
    burnRateSlowThreshold: 6

  # Policy Enforcer
  policy:
    freezeThresholdPercent: 20
    autoUnfreezeEnabled: true
    unfreezeThresholdPercent: 50
```

### Configuração do Operator

```yaml
operator:
  enabled: true
  replicas: 1  # Apenas 1 instância (active-passive)
  watchNamespaces: []  # Vazio = todos os namespaces
  reconciliationIntervalSeconds: 300  # 5 minutos
```

### High Availability

```yaml
replicaCount: 2  # Mínimo para HA

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 6
  targetCPUUtilizationPercentage: 70

podDisruptionBudget:
  enabled: true
  minAvailable: 1
```

## Integração com Alertmanager

### Configurar Webhook Receiver

1. Adicionar receiver ao Alertmanager ConfigMap:

```yaml
receivers:
  - name: sla-management-system-webhook
    webhook_configs:
      - url: http://sla-management-system.neural-hive-monitoring.svc.cluster.local:8000/webhooks/alertmanager
        send_resolved: true
```

2. Adicionar route:

```yaml
route:
  routes:
    - match_re:
        slo: ".*"
      receiver: sla-management-system-webhook
      group_by: [slo, service]
      group_wait: 10s
      repeat_interval: 4h
      continue: true
```

3. Aplicar configuração:

```bash
kubectl apply -f monitoring/alertmanager/sla-webhook-config.yaml
```

## Criando SLOs e Políticas

### Exemplo: SLO de Latência

```bash
kubectl apply -f examples/sla-management-system/example-slo-latency.yaml

# Verificar status
kubectl get slodefinition orchestrator-latency-slo -n neural-hive-orchestration -o yaml
```

### Exemplo: Política de Freeze

```bash
kubectl apply -f examples/sla-management-system/example-policy-orchestration-freeze.yaml

# Verificar status
kubectl get slapolicy orchestration-freeze-policy -n neural-hive-orchestration -o yaml
```

## Monitoramento

### Métricas Principais

```bash
# Port-forward para métricas
kubectl port-forward -n neural-hive-monitoring svc/sla-management-system 9090:9090

# Acessar
curl http://localhost:9090/metrics | grep sla_
```

Métricas importantes:
- `sla_calculations_total`: Total de cálculos executados
- `sla_budget_remaining_percent`: Budget restante por SLO
- `sla_burn_rate`: Taxa de consumo de budget
- `sla_freezes_active`: Freezes ativos
- `sla_postgresql_connection_errors_total`: Erros de conexão

### Dashboard Grafana

1. Importar dashboard:
```bash
kubectl apply -f monitoring/dashboards/sla-management-system.json
```

2. Acessar: Grafana → Dashboards → "SLA Management System - Operations Dashboard"

### Alertas

Alertas configurados:
- **SLAManagementSystemDown**: Sistema indisponível
- **CriticalBudgetExhausted**: Budget esgotado
- **HighBurnRateFast**: Consumo rápido de budget
- **FreezeActivated**: Freeze ativado
- **OperatorReconciliationErrors**: Erros no operator

## Validação

### Script de Validação

```bash
./scripts/validation/validate-sla-management-system.sh

# Com relatório
./scripts/validation/validate-sla-management-system.sh --report validation-report.json

# Verbose
./scripts/validation/validate-sla-management-system.sh --verbose
```

### Validação Manual

#### 1. Health Check

```bash
kubectl run curl-test --image=curlimages/curl --rm -it --restart=Never -- \
  curl http://sla-management-system.neural-hive-monitoring.svc.cluster.local:8000/health
```

Resposta esperada:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2025-01-15T10:00:00Z"
}
```

#### 2. Ready Check

```bash
kubectl run curl-test --image=curlimages/curl --rm -it --restart=Never -- \
  curl http://sla-management-system.neural-hive-monitoring.svc.cluster.local:8000/ready
```

Resposta esperada:
```json
{
  "ready": true,
  "postgresql": "ok",
  "redis": "ok",
  "prometheus": "ok",
  "kafka": "ok"
}
```

#### 3. Listar SLOs

```bash
kubectl get slodefinitions --all-namespaces
```

## Troubleshooting

### Problema: Pods não iniciam

**Sintoma**: Pods em CrashLoopBackOff

**Diagnóstico**:
```bash
kubectl logs -n neural-hive-monitoring -l app.kubernetes.io/name=sla-management-system --tail=100
kubectl describe pod <pod-name> -n neural-hive-monitoring
```

**Soluções Comuns**:
- Verificar secrets: `kubectl get secret sla-management-system-secret -n neural-hive-monitoring`
- Verificar conectividade PostgreSQL/Redis
- Verificar recursos disponíveis

### Problema: Operator não sincroniza CRDs

**Sintoma**: `status.synced: false` em CRDs

**Diagnóstico**:
```bash
kubectl logs -n neural-hive-monitoring -l app.kubernetes.io/component=operator --tail=100
kubectl get slodefinition <name> -n <namespace> -o yaml
```

**Soluções**:
- Verificar RBAC permissions
- Verificar conectividade PostgreSQL
- Verificar logs do operator para erros

### Problema: Budget não atualiza

**Sintoma**: `status.budgetRemaining` não muda

**Diagnóstico**:
```bash
# Verificar cálculos
curl http://localhost:8000/api/v1/slos | jq '.[] | {name, last_calculated_at}'

# Verificar métricas Prometheus
curl http://localhost:9090/metrics | grep sla_calculations
```

**Soluções**:
- Verificar conectividade Prometheus
- Validar query PromQL no SLO
- Verificar interval de cálculo (default 30s)

## Upgrade

### Procedimento

1. Backup de CRDs:
```bash
kubectl get slodefinitions --all-namespaces -o yaml > slos-backup.yaml
kubectl get slapolicies --all-namespaces -o yaml > policies-backup.yaml
```

2. Atualizar chart:
```bash
helm upgrade sla-management-system ./helm-charts/sla-management-system \
  --namespace neural-hive-monitoring \
  --values helm-charts/sla-management-system/values.yaml \
  --wait
```

3. Verificar:
```bash
kubectl rollout status deployment/sla-management-system -n neural-hive-monitoring
./scripts/validation/validate-sla-management-system.sh
```

### Rollback

```bash
helm rollback sla-management-system -n neural-hive-monitoring
```

## Disaster Recovery

### Backup

**PostgreSQL** (automático via backup do cluster)
**CRDs**:
```bash
kubectl get slodefinitions --all-namespaces -o yaml > slos-backup-$(date +%Y%m%d).yaml
kubectl get slapolicies --all-namespaces -o yaml > policies-backup-$(date +%Y%m%d).yaml
```

### Restore

1. Reinstalar sistema
2. Restaurar CRDs:
```bash
kubectl apply -f slos-backup.yaml
kubectl apply -f policies-backup.yaml
```

## Segurança

### mTLS (Istio)

```yaml
istio:
  enabled: true
  mtls:
    mode: STRICT
```

### Network Policies

```yaml
networkPolicy:
  enabled: true
```

### Secrets Management

**Desenvolvimento**: Kubernetes Secrets
**Produção**: SealedSecrets ou External Secrets Operator

```bash
# Exemplo com SealedSecrets
kubeseal --format yaml < secret.yaml > sealed-secret.yaml
kubectl apply -f sealed-secret.yaml
```

## Performance Tuning

### Ajustar Intervalo de Cálculo

```yaml
config:
  calculator:
    calculationIntervalSeconds: 60  # Aumentar para reduzir carga
```

### Ajustar Pool de Conexões

```yaml
config:
  postgresql:
    poolMinSize: 5
    poolMaxSize: 20
```

### Ajustar HPA

```yaml
autoscaling:
  targetCPUUtilizationPercentage: 60  # Escalar mais cedo
  maxReplicas: 10  # Permitir mais réplicas
```

## Referências

- [README Principal](README.md)
- [Operational Runbook](OPERATIONAL_RUNBOOK.md)
- [Implementation Notes](IMPLEMENTATION_NOTES.md)
- [Documentação Neural Hive-Mind](../../docs/)
