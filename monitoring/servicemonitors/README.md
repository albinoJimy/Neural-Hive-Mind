# ServiceMonitors Standalone

Este diretório contém ServiceMonitors para componentes de infraestrutura que não possuem ServiceMonitor em seus Helm charts.

## Componentes Cobertos

### Infraestrutura
- **Kafka** (`kafka-servicemonitor.yaml`) - Métricas JMX do Kafka
- **Neo4j** (a criar se necessário) - Métricas do Neo4j
- **ClickHouse** (a criar se necessário) - Métricas do ClickHouse

### Componentes da Fase 1 (já possuem ServiceMonitor)

Os seguintes componentes **NÃO** precisam de ServiceMonitors standalone pois já possuem em seus Helm charts:

- ✅ Gateway de Intenções (`gateway-intencoes/templates/servicemonitor.yaml`)
- ✅ Semantic Translation Engine (`semantic-translation-engine/templates/servicemonitor.yaml`)
- ✅ Specialist Business (`specialist-business/templates/servicemonitor.yaml`)
- ✅ Specialist Technical (`specialist-technical/templates/servicemonitor.yaml`)
- ✅ Specialist Behavior (`specialist-behavior/templates/servicemonitor.yaml`)
- ✅ Specialist Evolution (`specialist-evolution/templates/servicemonitor.yaml`)
- ✅ Specialist Architecture (`specialist-architecture/templates/servicemonitor.yaml`)
- ✅ Consensus Engine (`consensus-engine/templates/servicemonitor.yaml`)
- ✅ Memory Layer API (`memory-layer-api/templates/servicemonitor.yaml`)
- ✅ MongoDB (`mongodb/templates/servicemonitor.yaml`)
- ✅ Redis (`redis-cluster/templates/servicemonitor.yaml`)

## Como Aplicar

```bash
# Aplicar todos os ServiceMonitors
kubectl apply -f monitoring/servicemonitors/

# Aplicar um ServiceMonitor específico
kubectl apply -f monitoring/servicemonitors/kafka-servicemonitor.yaml
```

## Verificar ServiceMonitors

```bash
# Listar todos os ServiceMonitors com label neural.hive/metrics
kubectl get servicemonitor -A -l neural.hive/metrics=enabled

# Verificar targets no Prometheus
kubectl port-forward -n neural-hive-observability svc/neural-hive-prometheus-kube-prometheus-prometheus 9090:9090
# Acessar: http://localhost:9090/targets
```

## Troubleshooting

### ServiceMonitor não aparece no Prometheus

1. Verificar se o ServiceMonitor tem a label `neural.hive/metrics: "enabled"`
2. Verificar se o selector do ServiceMonitor corresponde aos labels do Service
3. Verificar logs do Prometheus Operator:
   ```bash
   kubectl logs -n neural-hive-observability -l app.kubernetes.io/name=prometheus-operator
   ```

### Métricas não aparecem

1. Verificar se o pod expõe métricas na porta configurada:
   ```bash
   kubectl port-forward -n <namespace> <pod-name> 8080:8080
   curl http://localhost:8080/metrics
   ```
2. Verificar se o Service tem a porta `metrics` configurada
3. Verificar NetworkPolicies que podem estar bloqueando o scraping
