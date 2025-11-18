# Deployment da Stack de Observabilidade - Neural Hive-Mind

## Visão Geral

Este documento descreve o processo de deployment da stack de observabilidade do Neural Hive-Mind, incluindo Prometheus, Grafana e Jaeger.

## Componentes

### 1. Prometheus Stack
- **Prometheus**: Coleta e armazenamento de métricas
- **AlertManager**: Gerenciamento de alertas
- **Node Exporter**: Métricas de nodes
- **Kube State Metrics**: Métricas do Kubernetes

### 2. Grafana (Deployment Standalone)
- **Estratégia**: Chart Grafana standalone (não o embarcado no kube-prometheus-stack)
- **Motivo**: Maior flexibilidade de configuração e versionamento independente
- **Visualização**: Dashboards interativos
- **Datasources**: Prometheus, Jaeger
- **Alerting**: Unified alerting nativo

### 3. Jaeger
- **Distributed Tracing**: Rastreamento de requisições
- **OTLP Support**: OpenTelemetry Protocol
- **UI**: Interface web para análise de traces

## Pré-requisitos

### Ferramentas Necessárias
- `kubectl` (v1.24+)
- `helm` (v3.10+)
- `jq` (para processamento JSON)
- Cluster Kubernetes (Minikube, Kind, ou produção)

### Recursos Mínimos (Ambiente Local)
- CPU: 4 cores
- RAM: 8GB
- Disk: 50GB

### Recursos Recomendados (Produção)
- CPU: 8+ cores
- RAM: 16GB+
- Disk: 200GB+

## Deployment - Ambiente Local

### Passo 1: Preparar Configurações

Os arquivos `values-local.yaml` já foram criados para cada componente com recursos reduzidos:

```bash
ls -la helm-charts/prometheus-stack/values-local.yaml
ls -la helm-charts/grafana/values-local.yaml
ls -la helm-charts/jaeger/values-local.yaml
```

### Passo 2: Executar Deploy

**Opção A: Script Automatizado (Recomendado)**

```bash
./scripts/deploy/deploy-observability-local.sh
```

**Opção B: Deploy Manual**

```bash
# Criar namespace
kubectl create namespace neural-hive-observability
kubectl label namespace neural-hive-observability \
    neural.hive/component=observability \
    neural.hive/layer=observabilidade

# Adicionar repositórios Helm
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add jaegertracing https://jaegertracing.github.io/helm-charts
helm repo update

# Deploy Prometheus
helm upgrade --install neural-hive-prometheus ./helm-charts/prometheus-stack \
    --namespace neural-hive-observability \
    --values ./helm-charts/prometheus-stack/values-local.yaml \
    --wait --timeout=10m

# Deploy Grafana (standalone - não o embarcado no prom-stack)
# Decisão: Usar chart standalone para maior flexibilidade
helm upgrade --install neural-hive-grafana ./helm-charts/grafana \
    --namespace neural-hive-observability \
    --values ./helm-charts/grafana/values-local.yaml \
    --wait --timeout=5m

# Deploy Jaeger
helm upgrade --install neural-hive-jaeger ./helm-charts/jaeger \
    --namespace neural-hive-observability \
    --values ./helm-charts/jaeger/values-local.yaml \
    --wait --timeout=5m
```

### Passo 3: Validar Deployment

```bash
# Verificar pods
kubectl get pods -n neural-hive-observability

# Executar validação completa
./scripts/observability/validate-observability.sh
```

**Resultado esperado**: Todos os pods em `Running` (1/1 Ready)

### Passo 4: Importar Dashboards

```bash
# Iniciar port-forward do Grafana
kubectl port-forward -n neural-hive-observability svc/neural-hive-grafana 3000:80 &

# Aguardar 5 segundos
sleep 5

# Importar dashboards
./scripts/observability/import-dashboards.sh

# Matar port-forward
kill %1
```

**Dashboards importados**:
- Neural Hive Overview
- Specialists Cognitive Layer
- Consensus & Governance
- Data Governance
- Memory Layer Data Quality
- Infrastructure Overview
- E mais 22 dashboards...

### Passo 5: Aplicar ServiceMonitors

```bash
# Aplicar ServiceMonitors standalone (se necessário)
kubectl apply -f monitoring/servicemonitors/

# Verificar ServiceMonitors
kubectl get servicemonitor -A -l neural.hive/metrics=enabled
```

**Esperado**: Mínimo 9 ServiceMonitors (componentes da Fase 1)

## Acessar Serviços

### Prometheus

```bash
kubectl port-forward -n neural-hive-observability \
    svc/neural-hive-prometheus-kube-prometheus-prometheus 9090:9090
```

Acessar: http://localhost:9090

**Verificações**:
- Status → Targets: Verificar targets sendo scraped
- Graph: Executar query `up{job="neural-hive-services"}`

### Grafana

```bash
kubectl port-forward -n neural-hive-observability \
    svc/neural-hive-grafana 3000:80
```

Acessar: http://localhost:3000

**Credenciais**:
- Username: `admin`
- Password: `admin`

**Verificações**:
- Configuration → Data Sources: Verificar Prometheus e Jaeger conectados
- Dashboards → Browse: Verificar folder "Neural Hive-Mind"

### Jaeger

```bash
# Service criado pelo chart all-in-one: neural-hive-jaeger
kubectl port-forward -n neural-hive-observability \
    svc/neural-hive-jaeger 16686:16686
```

Acessar: http://localhost:16686

**Verificações**:
- Search: Buscar por service `semantic-translation-engine`
- System Architecture: Visualizar dependências

## Validar Coleta de Métricas

### 1. Verificar Targets no Prometheus

```bash
# Port-forward Prometheus
kubectl port-forward -n neural-hive-observability \
    svc/neural-hive-prometheus-kube-prometheus-prometheus 9090:9090 &

# Consultar targets via API
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.neural_hive_component != null) | {job: .labels.job, component: .labels.neural_hive_component, health: .health}'

# Matar port-forward
kill %1
```

**Esperado**: Targets com `health: "up"` para todos os componentes da Fase 1

### 2. Consultar Métricas Específicas

```bash
# Métricas dos Specialists
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_specialist_evaluations_total' | jq .

# Métricas do Consensus Engine
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_consensus_decisions_total' | jq .

# Métricas do STE
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_plans_generated_total' | jq .
```

### 3. Verificar Dashboards no Grafana

1. Acessar Grafana (http://localhost:3000)
2. Navegar para "Dashboards" → "Neural Hive-Mind"
3. Abrir "Specialists Cognitive Layer"
4. Verificar se os painéis mostram dados (pode levar alguns minutos)

### 4. Verificar Traces no Jaeger

1. Acessar Jaeger (http://localhost:16686)
2. Selecionar service: `semantic-translation-engine`
3. Clicar em "Find Traces"
4. Verificar se traces aparecem (requer tráfego no sistema)

## Troubleshooting

### Problema 1: Pods em CrashLoopBackOff

**Diagnóstico**:
```bash
kubectl get pods -n neural-hive-observability
kubectl describe pod -n neural-hive-observability <pod-name>
kubectl logs -n neural-hive-observability <pod-name> --previous
```

**Soluções Comuns**:
- **Recursos insuficientes**: Reduzir replicas ou recursos em values-local.yaml
- **PVC não bound**: Verificar StorageClass disponível (`kubectl get sc`)
- **Imagem não encontrada**: Verificar conectividade com registry

### Problema 2: ServiceMonitors não aparecem no Prometheus

**Diagnóstico**:
```bash
# Verificar ServiceMonitors
kubectl get servicemonitor -A -l neural.hive/metrics=enabled

# Verificar logs do Prometheus Operator
kubectl logs -n neural-hive-observability \
    -l app.kubernetes.io/name=prometheus-operator --tail=100
```

**Soluções**:
- Verificar label `neural.hive/metrics: "enabled"` no ServiceMonitor
- Verificar selector do ServiceMonitor corresponde aos labels do Service
- Verificar RBAC do Prometheus Operator

### Problema 3: Dashboards não mostram dados

**Diagnóstico**:
```bash
# Verificar datasource Prometheus no Grafana
kubectl port-forward -n neural-hive-observability svc/neural-hive-grafana 3000:80 &
curl -s -u admin:admin http://localhost:3000/api/datasources | jq .
```

**Soluções**:
- Verificar URL do datasource Prometheus está correto
- Testar conectividade: `curl http://neural-hive-prometheus-kube-prometheus-prometheus.neural-hive-observability.svc.cluster.local:9090/-/healthy`
- Verificar se métricas estão sendo coletadas no Prometheus

### Problema 4: Jaeger não mostra traces

**Diagnóstico**:
```bash
# Verificar se aplicações estão enviando traces
kubectl logs -n semantic-translation-engine \
    -l app.kubernetes.io/name=semantic-translation-engine | grep -i "trace\|jaeger"
```

**Soluções**:
- Verificar variável de ambiente `JAEGER_AGENT_HOST` nas aplicações
- Verificar se OTLP receivers estão habilitados no Jaeger
- Testar envio manual de trace via `jaeger-client`

## Deployment - Produção

Para ambiente de produção, usar `values.yaml` padrão com ajustes:

```bash
# Deploy com valores de produção
helm upgrade --install neural-hive-prometheus ./helm-charts/prometheus-stack \
    --namespace neural-hive-observability \
    --values ./helm-charts/prometheus-stack/values.yaml \
    --set global.environment=production \
    --wait --timeout=15m
```

**Diferenças de Produção**:
- Replicas: 2-3 (HA)
- Storage: 100Gi+ (Prometheus), 10Gi (Grafana)
- Retention: 30 dias (Prometheus)
- Ingress: Habilitado com TLS
- AlertManager: Integração com Slack/PagerDuty
- Backup: Habilitado (schedule diário)

## Manutenção

### Backup de Dashboards

```bash
# Exportar todos os dashboards
kubectl port-forward -n neural-hive-observability svc/neural-hive-grafana 3000:80 &

for uid in $(curl -s -u admin:admin http://localhost:3000/api/search | jq -r '.[].uid'); do
    curl -s -u admin:admin "http://localhost:3000/api/dashboards/uid/$uid" | \
        jq '.dashboard' > "backup-dashboard-$uid.json"
done

kill %1
```

### Atualizar Helm Charts

```bash
# Atualizar repositórios
helm repo update

# Verificar versões disponíveis
helm search repo prometheus-community/kube-prometheus-stack
helm search repo grafana/grafana
helm search repo jaegertracing/jaeger

# Atualizar (com cautela)
helm upgrade neural-hive-prometheus ./helm-charts/prometheus-stack \
    --namespace neural-hive-observability \
    --values ./helm-charts/prometheus-stack/values-local.yaml \
    --reuse-values
```

### Limpar Dados Antigos

```bash
# Prometheus (via API)
curl -X POST http://localhost:9090/api/v1/admin/tsdb/delete_series \
    -d 'match[]={__name__=~".+"}' \
    -d 'start=2024-01-01T00:00:00Z' \
    -d 'end=2024-06-01T00:00:00Z'

# Grafana (limpar dashboards não usados)
# Via UI: Dashboards → Manage → Selecionar → Delete
```

## Referências

- [Prometheus Operator Documentation](https://prometheus-operator.dev/)
- [Grafana Documentation](https://grafana.com/docs/grafana/latest/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)
- [Neural Hive-Mind Architecture](./PHASE1_ARCHITECTURE.md)
- [Monitoring Best Practices](./MONITORING_BEST_PRACTICES.md)
