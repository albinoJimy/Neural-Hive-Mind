# MCP Tool Catalog - Checklist de Deployment

**Versão**: 1.0.0
**Data**: 2025-10-04

---

## 📋 Pré-Requisitos

### Infraestrutura

- [ ] Kubernetes cluster disponível (1.28+)
- [ ] Namespace `neural-hive-mcp` criado
- [ ] MongoDB 6.0+ deployado
- [ ] Redis 7.0+ deployado
- [ ] Kafka 3.6+ deployado com Strimzi operator
- [ ] Prometheus operator instalado
- [ ] Grafana instalado

### Configurações

- [ ] Service Registry disponível
- [ ] OpenTelemetry Collector deployado
- [ ] Container registry configurado (ex: registry/neural-hive-mind/)

---

## 🚀 Etapas de Deployment

### 1. Criar Kafka Topics

```bash
# Aplicar manifestos
kubectl apply -f k8s/kafka-topics/mcp-tool-selection-requests-topic.yaml
kubectl apply -f k8s/kafka-topics/mcp-tool-selection-responses-topic.yaml

# Verificar criação
kubectl get kafkatopics -n neural-hive-kafka
```

**Checklist**:
- [ ] Topic `mcp.tool.selection.requests` criado (3 partitions, replication=3)
- [ ] Topic `mcp.tool.selection.responses` criado (3 partitions, replication=3)

---

### 2. Build e Push Docker Image

```bash
# Build
cd services/mcp-tool-catalog
docker build -t registry/neural-hive-mind/mcp-tool-catalog:1.0.0 .

# Tag latest
docker tag registry/neural-hive-mind/mcp-tool-catalog:1.0.0 \
  registry/neural-hive-mind/mcp-tool-catalog:latest

# Push
docker push registry/neural-hive-mind/mcp-tool-catalog:1.0.0
docker push registry/neural-hive-mind/mcp-tool-catalog:latest
```

**Checklist**:
- [ ] Imagem buildada com sucesso
- [ ] Imagem taggeada com versão
- [ ] Imagem enviada para registry

---

### 3. Criar Secrets Kubernetes

```bash
# MongoDB credentials
kubectl create secret generic mcp-mongodb-secret \
  --from-literal=username=mcp_user \
  --from-literal=password=<STRONG_PASSWORD> \
  --namespace=neural-hive-mcp

# Redis credentials (se autenticado)
kubectl create secret generic mcp-redis-secret \
  --from-literal=password=<REDIS_PASSWORD> \
  --namespace=neural-hive-mcp

# Service Registry credentials
kubectl create secret generic mcp-service-registry-secret \
  --from-literal=token=<SERVICE_REGISTRY_TOKEN> \
  --namespace=neural-hive-mcp
```

**Checklist**:
- [ ] Secret MongoDB criado
- [ ] Secret Redis criado (se aplicável)
- [ ] Secret Service Registry criado

---

### 4. Configurar ConfigMap

```bash
kubectl create configmap mcp-tool-catalog-config \
  --from-literal=KAFKA_BOOTSTRAP_SERVERS=kafka-cluster-kafka-bootstrap:9092 \
  --from-literal=MONGODB_URL=mongodb://mongodb-svc:27017 \
  --from-literal=REDIS_URL=redis://redis-cluster:6379 \
  --from-literal=SERVICE_REGISTRY_HOST=service-registry-svc \
  --from-literal=SERVICE_REGISTRY_PORT=8080 \
  --from-literal=GA_POPULATION_SIZE=50 \
  --from-literal=GA_MAX_GENERATIONS=100 \
  --from-literal=GA_TIMEOUT_SECONDS=30 \
  --from-literal=CACHE_TTL_SECONDS=3600 \
  --namespace=neural-hive-mcp
```

**Checklist**:
- [ ] ConfigMap criado com configurações corretas

---

### 5. Deploy via Helm

```bash
cd helm-charts/mcp-tool-catalog

# Validar values.yaml
helm lint .

# Dry-run
helm upgrade --install mcp-tool-catalog . \
  --namespace neural-hive-mcp \
  --dry-run --debug

# Deploy real
helm upgrade --install mcp-tool-catalog . \
  --namespace neural-hive-mcp \
  --create-namespace \
  --wait --timeout=5m

# Verificar status
helm status mcp-tool-catalog -n neural-hive-mcp
```

**Checklist**:
- [ ] Helm chart validado (lint)
- [ ] Dry-run executado sem erros
- [ ] Deploy realizado com sucesso
- [ ] Pods em estado Running

---

### 6. Verificar Deployment

```bash
# Verificar pods
kubectl get pods -n neural-hive-mcp -l app.kubernetes.io/name=mcp-tool-catalog

# Verificar logs
kubectl logs -n neural-hive-mcp -l app.kubernetes.io/name=mcp-tool-catalog --tail=50

# Verificar service
kubectl get svc -n neural-hive-mcp mcp-tool-catalog
```

**Checklist**:
- [ ] Pods em estado Running (min 2 replicas)
- [ ] Logs sem erros críticos
- [ ] Service criado corretamente

---

### 7. Health Checks

```bash
# Port-forward para teste local
kubectl port-forward -n neural-hive-mcp svc/mcp-tool-catalog 8080:8080

# Health check
curl http://localhost:8080/health
# Esperado: {"status":"healthy"}

# Ready check
curl http://localhost:8080/ready
# Esperado: {"status":"ready"}

# Listar ferramentas
curl http://localhost:8080/api/v1/tools | jq '.total'
# Esperado: 87
```

**Checklist**:
- [ ] Endpoint `/health` respondendo
- [ ] Endpoint `/ready` respondendo
- [ ] API `/api/v1/tools` retornando 87 ferramentas

---

### 8. Validação Completa

```bash
# Executar script de validação
cd scripts/validation
./validate-mcp-tool-catalog.sh
```

**Checklist**:
- [ ] ✅ Pré-requisitos OK
- [ ] ✅ Deployment OK
- [ ] ✅ Service OK
- [ ] ✅ Health Checks OK
- [ ] ✅ Catálogo de Ferramentas OK
- [ ] ✅ MongoDB Persistence OK
- [ ] ✅ Redis Cache OK
- [ ] ✅ Service Registry OK
- [ ] ✅ Observabilidade OK

---

### 9. Configurar Prometheus Scraping

```bash
# Aplicar ServiceMonitor
kubectl apply -f k8s/servicemonitor.yaml

# Verificar scraping
kubectl get servicemonitor -n neural-hive-mcp mcp-tool-catalog
```

**Checklist**:
- [ ] ServiceMonitor criado
- [ ] Prometheus descobrindo target
- [ ] Métricas sendo coletadas

---

### 10. Importar Dashboard Grafana

```bash
# Via UI
# 1. Grafana → Dashboards → Import
# 2. Upload: observability/grafana/dashboards/mcp-tool-catalog.json
# 3. Selecionar datasource Prometheus
# 4. Import

# Ou via ConfigMap
kubectl create configmap mcp-grafana-dashboard \
  --from-file=mcp-tool-catalog.json=observability/grafana/dashboards/mcp-tool-catalog.json \
  --namespace=neural-hive-monitoring
```

**Checklist**:
- [ ] Dashboard importado no Grafana
- [ ] 4 rows visíveis (Overview, GA, Execution, Health)
- [ ] Métricas aparecendo corretamente

---

### 11. Configurar Alertas Prometheus

```bash
# Aplicar PrometheusRule
kubectl apply -f observability/prometheus/alerts/mcp-tool-catalog-alerts.yaml

# Verificar regras
kubectl get prometheusrule -n neural-hive-monitoring mcp-tool-catalog-alerts
```

**Checklist**:
- [ ] PrometheusRule aplicado
- [ ] 10 alertas configurados
- [ ] Alertas visíveis no Prometheus UI

---

### 12. Teste End-to-End

```bash
# Executar teste E2E
cd tests
./phase2-mcp-integration-test.sh
```

**Checklist**:
- [ ] Etapa 1: Intent Envelope ✓
- [ ] Etapa 2: Cognitive Plan ✓
- [ ] Etapa 3: Consolidated Decision ✓
- [ ] Etapa 4: Execution Ticket ✓
- [ ] Etapa 5: Seleção MCP ✓
- [ ] Etapa 6: Code Forge Pipeline ✓
- [ ] Etapa 7: Artefato Gerado ✓
- [ ] Etapa 8: Feedback Loop ✓
- [ ] Etapa 9: Métricas ✓
- [ ] Etapa 10: Traces ✓

---

## 🔧 Troubleshooting

### Pods CrashLooping

```bash
# Ver logs
kubectl logs -n neural-hive-mcp <pod-name> --previous

# Verificar eventos
kubectl describe pod -n neural-hive-mcp <pod-name>

# Verificar secrets
kubectl get secrets -n neural-hive-mcp
```

**Possíveis Causas**:
- [ ] MongoDB não acessível
- [ ] Redis não acessível
- [ ] Kafka não acessível
- [ ] Secret ausente ou inválido
- [ ] Imagem Docker incorreta

---

### Genetic Algorithm Timeout

```bash
# Ajustar timeout
kubectl set env deployment/mcp-tool-catalog GA_TIMEOUT_SECONDS=60 -n neural-hive-mcp

# Reduzir generations
kubectl set env deployment/mcp-tool-catalog GA_MAX_GENERATIONS=50 -n neural-hive-mcp

# Restart pods
kubectl rollout restart deployment/mcp-tool-catalog -n neural-hive-mcp
```

---

### API não respondendo

```bash
# Verificar service
kubectl get svc -n neural-hive-mcp mcp-tool-catalog

# Verificar endpoints
kubectl get endpoints -n neural-hive-mcp mcp-tool-catalog

# Port-forward direto para pod
kubectl port-forward -n neural-hive-mcp <pod-name> 8080:8080

# Testar
curl http://localhost:8080/health
```

---

### Métricas não aparecendo

```bash
# Verificar ServiceMonitor
kubectl get servicemonitor -n neural-hive-mcp mcp-tool-catalog -o yaml

# Verificar targets Prometheus
# Prometheus UI → Status → Targets
# Procurar por: neural-hive-mcp/mcp-tool-catalog

# Verificar labels
kubectl get pods -n neural-hive-mcp --show-labels | grep mcp-tool-catalog
```

---

## ✅ Checklist Final de Validação

### Funcionalidade Core
- [ ] Serviço deployado e running (min 2 replicas)
- [ ] Health checks respondendo
- [ ] API REST operacional
- [ ] 87 ferramentas no catálogo
- [ ] Kafka consumer/producer conectados

### Algoritmo Genético
- [ ] Seleções executando sem timeout
- [ ] Fitness scores calculados corretamente
- [ ] Cache funcionando (Redis)

### Observabilidade
- [ ] 17 métricas Prometheus coletadas
- [ ] Dashboard Grafana exibindo dados
- [ ] 10 alertas configurados
- [ ] Logs estruturados em JSON

### Integração
- [ ] MongoDB persistindo ferramentas
- [ ] Redis cacheando seleções
- [ ] Kafka produzindo/consumindo mensagens
- [ ] Service Registry com heartbeat

---

## 📊 Métricas de Sucesso

### Performance
- [ ] p95 de seleção GA < 5s
- [ ] Cache hit rate > 70%
- [ ] API latency p95 < 100ms

### Confiabilidade
- [ ] Uptime > 99.9%
- [ ] Zero CrashLoopBackOff em 24h
- [ ] Consumo de memória < 90%

### Qualidade
- [ ] Taxa de falha de seleção < 1%
- [ ] Taxa de sucesso de execução > 95%
- [ ] Diversity score médio > 0.7

---

## 📝 Próximos Passos Pós-Deploy

### Curto Prazo (1 semana)
- [ ] Monitorar métricas por 48h
- [ ] Ajustar parâmetros GA se necessário
- [ ] Validar integração com Code Forge

### Médio Prazo (1 mês)
- [ ] Implementar HPA baseado em CPU/memória
- [ ] Adicionar PodDisruptionBudget
- [ ] Otimizar performance do GA

### Longo Prazo (3 meses)
- [ ] Implementar GRPCAdapter
- [ ] Implementar LibraryAdapter
- [ ] Machine Learning para warm-start do GA

---

**Responsável pelo Deploy**: _________________
**Data de Deploy**: _________________
**Versão Deployada**: 1.0.0
**Status Final**: [ ] Aprovado  [ ] Com Pendências
