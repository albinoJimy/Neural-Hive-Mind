# Flow C Operations Runbook

## Overview

Procedimentos operacionais para Flow C - Orquestração de Execução Adaptativa. Este runbook cobre operações diárias, scaling, manutenção e procedimentos de emergência para todos os componentes do Flow C.

---

## Configuração do Ambiente

Configure estas variáveis antes de executar os comandos. Os valores mostrados são padrões baseados nas configurações dos Helm charts.

```bash
# Namespaces
export ORCHESTRATION_NS="neural-hive-orchestration"
export EXECUTION_NS="neural-hive-execution"
export REGISTRY_NS="neural-hive-registry"
export KAFKA_NS="kafka"
export MONGODB_NS="mongodb-cluster"
export REDIS_NS="redis-cluster"
export MONITORING_NS="monitoring"

# Nomes dos Releases Helm (usados para nomenclatura de ConfigMaps)
export ORCHESTRATOR_RELEASE="orchestrator-dynamic"
export WORKER_RELEASE="worker-agents"

# Nomes dos ConfigMaps (gerados pelo Helm: <release>-config para orchestrator, <release> para workers)
export ORCHESTRATOR_CONFIG="${ORCHESTRATOR_RELEASE}-config"
export WORKER_CONFIG="${WORKER_RELEASE}"

# Configuração Kafka (do values.yaml do Helm)
export KAFKA_BOOTSTRAP="neural-hive-kafka-kafka-bootstrap.${KAFKA_NS}.svc.cluster.local:9092"
export KAFKA_POD="neural-hive-kafka-kafka-0"

# Configuração MongoDB (do values.yaml do Helm)
# NOTA: Obtenha credenciais reais do Kubernetes secrets ou Vault
export MONGODB_HOST="mongodb-0.mongodb-headless.${MONGODB_NS}.svc.cluster.local:27017"
export MONGODB_DATABASE="neural_hive_orchestration"
# Obter URI do MongoDB do secret do orchestrator (contém autenticação)
# kubectl get secret ${ORCHESTRATOR_RELEASE}-secrets -n ${ORCHESTRATION_NS} -o jsonpath='{.data.MONGODB_URI}' | base64 -d

# Configuração Redis
export REDIS_POD="redis-cluster-0"
export REDIS_HOST="redis-cluster.${REDIS_NS}.svc.cluster.local:6379"

# Notas sobre Ferramentas:
# - Comandos Kafka (kafka-topics.sh, kafka-console-consumer.sh): Executar do ${KAFKA_POD} em ${KAFKA_NS}
# - Comandos MongoDB (mongosh): Executar do pod mongodb em ${MONGODB_NS}
# - Comandos Redis (redis-cli): Executar do ${REDIS_POD} em ${REDIS_NS}
# - grpcurl: Usar port-forward local + grpcurl instalado localmente
# - temporal CLI: Disponível nos pods do orchestrator
```

---

## Service Inventory

### Orchestrator Dynamic
- **Namespace:** neural-hive-orchestration
- **Deployment:** orchestrator-dynamic
- **Health Endpoints:** /health, /ready
- **Ports:** 8000 (HTTP), 50051 (gRPC)
- **Dependencies:** Temporal, MongoDB, Kafka, Redis, Service Registry

### Worker Agents
- **Namespace:** neural-hive-execution
- **Deployment:** worker-agents
- **Health Endpoint:** /health
- **Ports:** 8080 (HTTP), 50052 (gRPC)
- **Dependencies:** Kafka, Code Forge, ArgoCD, Vault

### Service Registry
- **Namespace:** neural-hive-registry
- **Deployment:** service-registry
- **Health Endpoint:** /health
- **Ports:** 50051 (gRPC)
- **Dependencies:** etcd, Redis

### Execution Ticket Service
- **Namespace:** neural-hive-orchestration
- **Deployment:** execution-ticket-service
- **Health Endpoint:** /health
- **Ports:** 8001 (HTTP), 50052 (gRPC)
- **Dependencies:** PostgreSQL, MongoDB

---

## Common Operations

### Start/Stop Services

#### Start All Flow C Services

```bash
# Start in dependency order
kubectl scale deployment service-registry --replicas=3 -n neural-hive-registry
kubectl scale deployment execution-ticket-service --replicas=2 -n neural-hive-orchestration
kubectl scale deployment orchestrator-dynamic --replicas=2 -n neural-hive-orchestration
kubectl scale deployment worker-agents --replicas=3 -n neural-hive-execution

# Wait for readiness
kubectl wait --for=condition=ready pod -l app=service-registry -n neural-hive-registry --timeout=120s
kubectl wait --for=condition=ready pod -l app=execution-ticket-service -n neural-hive-orchestration --timeout=120s
kubectl wait --for=condition=ready pod -l app=orchestrator-dynamic -n neural-hive-orchestration --timeout=120s
kubectl wait --for=condition=ready pod -l app=worker-agents -n neural-hive-execution --timeout=120s
```

#### Stop All Flow C Services

```bash
# Stop in reverse dependency order
kubectl scale deployment worker-agents --replicas=0 -n neural-hive-execution
kubectl scale deployment orchestrator-dynamic --replicas=0 -n neural-hive-orchestration
kubectl scale deployment execution-ticket-service --replicas=0 -n neural-hive-orchestration
kubectl scale deployment service-registry --replicas=0 -n neural-hive-registry
```

#### Graceful Restart

```bash
# Restart with zero downtime (rolling update)
kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration
kubectl rollout restart deployment/worker-agents -n neural-hive-execution

# Monitor rollout status
kubectl rollout status deployment/orchestrator-dynamic -n neural-hive-orchestration
kubectl rollout status deployment/worker-agents -n neural-hive-execution
```

---

### Scale Operations

#### Scale Orchestrator Dynamic

```bash
# Manual scaling
kubectl scale deployment orchestrator-dynamic --replicas=5 -n neural-hive-orchestration

# Verify HPA status
kubectl get hpa orchestrator-dynamic -n neural-hive-orchestration

# Adjust HPA limits
kubectl patch hpa orchestrator-dynamic -n neural-hive-orchestration -p '{"spec":{"minReplicas":2,"maxReplicas":10}}'
```

#### Scale Worker Agents

```bash
# Escalar workers baseado em carga
kubectl scale deployment worker-agents --replicas=10 -n ${EXECUTION_NS}

# Verificar registro de workers no Service Registry (via métricas ou logs)
kubectl logs -n ${REGISTRY_NS} -l app=service-registry --tail=50 | grep -i "worker.*register"

# Alternativa: Verificar quantidade de pods worker em execução
kubectl get pods -n ${EXECUTION_NS} -l app=worker-agents -o wide
```

#### Auto-scaling Configuration

```bash
# View current HPA configuration
kubectl get hpa -n neural-hive-orchestration -o yaml

# Adjust HPA for orchestrator
kubectl patch hpa orchestrator-dynamic -n neural-hive-orchestration --type merge -p '{
  "spec": {
    "minReplicas": 2,
    "maxReplicas": 10,
    "metrics": [{
      "type": "Resource",
      "resource": {
        "name": "cpu",
        "target": {"type": "Utilization", "averageUtilization": 70}
      }
    }]
  }
}'

# Adjust HPA for workers
kubectl patch hpa worker-agents -n neural-hive-execution --type merge -p '{
  "spec": {
    "minReplicas": 3,
    "maxReplicas": 20,
    "metrics": [{
      "type": "Resource",
      "resource": {
        "name": "cpu",
        "target": {"type": "Utilization", "averageUtilization": 60}
      }
    }]
  }
}'
```

---

### Logs and Debugging

#### View Logs

```bash
# Orchestrator Dynamic logs
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=100 -f

# Filter by correlation_id
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=1000 | grep "correlation_id=abc-123"

# Filter by log level
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=500 | grep "level=error"

# Worker Agents logs
kubectl logs -n neural-hive-execution -l app=worker-agents --tail=100 -f

# Service Registry logs
kubectl logs -n neural-hive-registry -l app=service-registry --tail=100 -f

# Execution Ticket Service logs
kubectl logs -n neural-hive-orchestration -l app=execution-ticket-service --tail=100 -f
```

#### Debug Temporal Workflows

```bash
# List running workflows
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  temporal workflow list --namespace default

# Describe specific workflow
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  temporal workflow describe --workflow-id flow-c-abc-123

# Query workflow state
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  temporal workflow query --workflow-id flow-c-abc-123 --query-type get_status

# View workflow history
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  temporal workflow show --workflow-id flow-c-abc-123

# List failed workflows
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  temporal workflow list --namespace default --query 'ExecutionStatus="Failed"' --limit 20
```

---

### Health Checks

#### Check Service Health

```bash
# Orchestrator Dynamic
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  curl -s http://localhost:8000/health | jq

# Orchestrator Dynamic readiness
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  curl -s http://localhost:8000/ready | jq

# Worker Agents
kubectl exec -n neural-hive-execution deployment/worker-agents -- \
  curl -s http://localhost:8080/health | jq

# Service Registry (gRPC)
kubectl exec -n neural-hive-registry deployment/service-registry -- \
  grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check

# Execution Ticket Service
kubectl exec -n neural-hive-orchestration deployment/execution-ticket-service -- \
  curl -s http://localhost:8001/health | jq
```

#### Verificar Dependências

**NOTA:** Os pods de aplicação não contêm ferramentas como kafka-*, redis-cli ou grpcurl.
Use os pods específicos de cada serviço ou port-forward para testar conectividade.

```bash
# MongoDB connectivity (via Python no orchestrator - pymongo está disponível)
kubectl exec -n ${ORCHESTRATION_NS} deployment/orchestrator-dynamic -- \
  python -c "import os; from pymongo import MongoClient; uri=os.environ.get('MONGODB_URI','mongodb://localhost:27017'); print(MongoClient(uri, serverSelectionTimeoutMS=5000).server_info())"

# Kafka connectivity (executar do pod Kafka)
kubectl exec -n ${KAFKA_NS} ${KAFKA_POD} -- \
  kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic plans.consensus --max-messages 1 --timeout-ms 5000

# Temporal connectivity (temporal CLI disponível no orchestrator)
kubectl exec -n ${ORCHESTRATION_NS} deployment/orchestrator-dynamic -- \
  temporal workflow list --namespace neural-hive-mind --limit 1

# Redis connectivity (executar do pod Redis)
kubectl exec -n redis-cluster ${REDIS_POD} -- redis-cli PING

# Service Registry connectivity (via port-forward + grpcurl local, ou use Python no orchestrator)
kubectl exec -n ${ORCHESTRATION_NS} deployment/orchestrator-dynamic -- \
  python -c "import grpc; from proto import service_registry_pb2_grpc; ch=grpc.insecure_channel('service-registry.${REGISTRY_NS}:50051'); print('gRPC channel OK')"

# Alternativa: Port-forward para testes locais com grpcurl
# kubectl port-forward -n ${REGISTRY_NS} svc/service-registry 50051:50051
# grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check

# etcd connectivity (do pod Service Registry, se etcdctl disponível)
# Ou use port-forward: kubectl port-forward -n ${REGISTRY_NS} svc/etcd 2379:2379
```

---

### Metrics and Monitoring

#### Query Prometheus Metrics

```bash
# Flow C latency (p95)
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=histogram_quantile(0.95,rate(neural_hive_flow_c_duration_seconds_bucket[5m]))" | jq '.data.result[0].value[1]'

# Flow C latency (p99)
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=histogram_quantile(0.99,rate(neural_hive_flow_c_duration_seconds_bucket[5m]))" | jq '.data.result[0].value[1]'

# Flow C success rate
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=rate(neural_hive_flow_c_success_total[10m])/(rate(neural_hive_flow_c_success_total[10m])+rate(neural_hive_flow_c_failures_total[10m]))" | jq

# Workers available
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=count(neural_hive_service_registry_agents_total{agent_type=\"worker\",status=\"healthy\"})" | jq

# Tickets generated (rate per minute)
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=rate(neural_hive_execution_tickets_created_total{source=\"flow_c\"}[5m])*60" | jq

# Active workflows
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_flow_c_active_workflows" | jq

# SLA violations
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=rate(neural_hive_flow_c_sla_violations_total[30m])" | jq

# Circuit breaker state
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_circuit_breaker_state{component=\"orchestrator\"}" | jq
```

#### Access Dashboards

```bash
# Port-forward Grafana
kubectl port-forward -n monitoring svc/grafana 3000:80

# Open dashboards
# - Flow C Orchestration: http://localhost:3000/d/flow-c-orchestration
# - Flow C Security: http://localhost:3000/d/flow-c-security
# - Flow C ML: http://localhost:3000/d/flow-c-ml
# - Service Registry: http://localhost:3000/d/service-registry

# Port-forward Prometheus
kubectl port-forward -n monitoring svc/prometheus 9090:9090
# Access: http://localhost:9090
```

---

### Configuration Management

#### Update ConfigMap

```bash
# View current orchestrator config (ConfigMap name: <release>-config)
kubectl get configmap ${ORCHESTRATOR_CONFIG} -n ${ORCHESTRATION_NS} -o yaml

# Alternative: Find ConfigMap by label selector
kubectl get configmap -n ${ORCHESTRATION_NS} -l app.kubernetes.io/name=orchestrator-dynamic -o yaml

# Edit orchestrator config
kubectl edit configmap ${ORCHESTRATOR_CONFIG} -n ${ORCHESTRATION_NS}

# Apply config changes (requires restart)
kubectl rollout restart deployment/orchestrator-dynamic -n ${ORCHESTRATION_NS}

# View worker config (ConfigMap name: <release>)
kubectl get configmap ${WORKER_CONFIG} -n ${EXECUTION_NS} -o yaml

# Alternative: Find ConfigMap by label selector
kubectl get configmap -n ${EXECUTION_NS} -l app.kubernetes.io/name=worker-agents -o yaml

# Edit worker config
kubectl edit configmap ${WORKER_CONFIG} -n ${EXECUTION_NS}
kubectl rollout restart deployment/worker-agents -n ${EXECUTION_NS}
```

#### Update Secrets

```bash
# Update MongoDB credentials
kubectl create secret generic mongodb-credentials \
  --from-literal=username=orchestrator \
  --from-literal=password=new-secure-password \
  --dry-run=client -o yaml | kubectl apply -f - -n neural-hive-orchestration

# Update Kafka credentials
kubectl create secret generic kafka-credentials \
  --from-literal=username=orchestrator \
  --from-literal=password=new-secure-password \
  --dry-run=client -o yaml | kubectl apply -f - -n neural-hive-orchestration

# Update Code Forge webhook secret
kubectl create secret generic code-forge-secrets \
  --from-literal=webhook-secret=new-secret-value \
  --dry-run=client -o yaml | kubectl apply -f - -n neural-hive-execution

# Restart affected services
kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration
kubectl rollout restart deployment/worker-agents -n neural-hive-execution
```

---

### Database Operations

#### MongoDB Queries

**NOTE:** MongoDB commands must be run from the MongoDB pod in the `mongodb-cluster` namespace.
The database name is `neural_hive_orchestration` and requires authentication.

```bash
# Get MongoDB credentials from orchestrator secret
MONGODB_URI=$(kubectl get secret ${ORCHESTRATOR_RELEASE}-secrets -n ${ORCHESTRATION_NS} \
  -o jsonpath='{.data.MONGODB_URI}' 2>/dev/null | base64 -d || echo "mongodb://localhost:27017")

# Count execution tickets (run from MongoDB pod)
kubectl exec -n ${MONGODB_NS} mongodb-0 -- \
  mongosh "${MONGODB_URI}" --eval 'db.getSiblingDB("neural_hive_orchestration").execution_tickets.countDocuments({})'

# Find tickets by plan_id
kubectl exec -n ${MONGODB_NS} mongodb-0 -- \
  mongosh "${MONGODB_URI}" --eval 'db.getSiblingDB("neural_hive_orchestration").execution_tickets.find({plan_id: "plan-123"}).pretty()'

# Find tickets by status
kubectl exec -n ${MONGODB_NS} mongodb-0 -- \
  mongosh "${MONGODB_URI}" --eval 'db.getSiblingDB("neural_hive_orchestration").execution_tickets.find({status: "RUNNING"}).limit(10).pretty()'

# Check validation audit
kubectl exec -n ${MONGODB_NS} mongodb-0 -- \
  mongosh "${MONGODB_URI}" --eval 'db.getSiblingDB("neural_hive_orchestration").validation_audit.find().sort({timestamp: -1}).limit(10).pretty()'

# Check workflow results
kubectl exec -n ${MONGODB_NS} mongodb-0 -- \
  mongosh "${MONGODB_URI}" --eval 'db.getSiblingDB("neural_hive_orchestration").workflow_results.find().sort({completed_at: -1}).limit(10).pretty()'

# Get collection stats
kubectl exec -n ${MONGODB_NS} mongodb-0 -- \
  mongosh "${MONGODB_URI}" --eval 'db.getSiblingDB("neural_hive_orchestration").execution_tickets.stats()'

# Check indexes
kubectl exec -n ${MONGODB_NS} mongodb-0 -- \
  mongosh "${MONGODB_URI}" --eval 'db.getSiblingDB("neural_hive_orchestration").execution_tickets.getIndexes()'

# Alternative: Use port-forward for local mongosh access
# kubectl port-forward -n ${MONGODB_NS} svc/mongodb-headless 27017:27017
# mongosh "mongodb://root:<password>@localhost:27017/?replicaSet=rs0" --authenticationDatabase admin
```

#### Redis Operations

**NOTE:** Redis is deployed as a cluster in the `redis-cluster` namespace.

```bash
# Check idempotency keys (run from Redis pod)
kubectl exec -n redis-cluster ${REDIS_POD} -- redis-cli KEYS "decision:processed:*"
kubectl exec -n redis-cluster ${REDIS_POD} -- redis-cli KEYS "ticket:processed:*"

# Count idempotency keys
kubectl exec -n redis-cluster ${REDIS_POD} -- redis-cli KEYS "decision:processed:*" | wc -l

# Check TTL
kubectl exec -n redis-cluster ${REDIS_POD} -- redis-cli TTL "decision:processed:decision-123"

# Check pheromone cache
kubectl exec -n redis-cluster ${REDIS_POD} -- redis-cli KEYS "pheromone:*"

# Check telemetry buffer size
kubectl exec -n redis-cluster ${REDIS_POD} -- redis-cli KEYS "telemetry:buffer:*" | wc -l

# Get database size
kubectl exec -n redis-cluster ${REDIS_POD} -- redis-cli DBSIZE

# Get memory usage
kubectl exec -n redis-cluster ${REDIS_POD} -- redis-cli INFO memory

# Clear cache (use with caution - only in emergency)
# kubectl exec -n redis-cluster ${REDIS_POD} -- redis-cli FLUSHDB

# Alternative: Use port-forward for local redis-cli access
# kubectl port-forward -n redis-cluster svc/redis-cluster 6379:6379
# redis-cli -h localhost -p 6379
```

#### Kafka Operations

**NOTA:** Comandos Kafka devem ser executados a partir do pod Kafka no namespace `kafka`.

```bash
# Listar tópicos
kubectl exec -n ${KAFKA_NS} ${KAFKA_POD} -- \
  kafka-topics.sh --bootstrap-server localhost:9092 --list

# Descrever tópico
kubectl exec -n ${KAFKA_NS} ${KAFKA_POD} -- \
  kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic execution.tickets

# Verificar lag do consumer group
kubectl exec -n ${KAFKA_NS} ${KAFKA_POD} -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group orchestrator-dynamic

# Verificar membros do consumer group
kubectl exec -n ${KAFKA_NS} ${KAFKA_POD} -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group worker-consumers --members

# Ler mensagens recentes do tópico
kubectl exec -n ${KAFKA_NS} ${KAFKA_POD} -- \
  kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic execution.tickets --from-beginning --max-messages 5
```

---

## Maintenance Windows

### Pre-Maintenance Checklist

- [ ] Notify stakeholders via #neural-hive-ops Slack channel
- [ ] Create incident in PagerDuty (scheduled maintenance)
- [ ] Silence alerts in Alertmanager

```bash
# Silence Flow C alerts for maintenance window
kubectl exec -n monitoring alertmanager-0 -- amtool silence add \
  alertname=~"FlowC.*" \
  --duration=2h \
  --comment="Scheduled maintenance" \
  --author="$(whoami)"
```

- [ ] Backup de coleções MongoDB

```bash
# Obter URI do MongoDB do secret (com autenticação)
MONGODB_URI=$(kubectl get secret ${ORCHESTRATOR_RELEASE}-secrets -n ${ORCHESTRATION_NS} \
  -o jsonpath='{.data.MONGODB_URI}' 2>/dev/null | base64 -d)

# Executar backup do pod MongoDB
kubectl exec -n ${MONGODB_NS} mongodb-0 -- \
  mongodump --uri "${MONGODB_URI}" --db ${MONGODB_DATABASE} --out /tmp/backup-$(date +%Y%m%d-%H%M)
```

- [ ] Documentar offsets dos consumer groups Kafka

```bash
kubectl exec -n ${KAFKA_NS} ${KAFKA_POD} -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --all-groups > /tmp/kafka-offsets-backup.txt
```

- [ ] Scale down non-critical services (if needed)

### Post-Maintenance Checklist

- [ ] Verify all services healthy

```bash
kubectl get pods -n neural-hive-orchestration
kubectl get pods -n neural-hive-execution
kubectl get pods -n neural-hive-registry
```

- [ ] Check Temporal workflows resumed

```bash
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  temporal workflow list --namespace default --query 'ExecutionStatus="Running"' --limit 10
```

- [ ] Validate metrics in Prometheus

```bash
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=up{job=~\"orchestrator-dynamic|worker-agents\"}" | jq
```

- [ ] Un-silence alerts

```bash
# List active silences
kubectl exec -n monitoring alertmanager-0 -- amtool silence query

# Expire silence by ID
kubectl exec -n monitoring alertmanager-0 -- amtool silence expire <silence-id>
```

- [ ] Monitor for 30 minutes for any anomalies
- [ ] Update stakeholders on maintenance completion

---

## Emergency Procedures

### Circuit Breaker Aberto

```bash
# Verificar estado do circuit breaker
kubectl logs -n ${ORCHESTRATION_NS} -l app=orchestrator-dynamic --tail=100 | grep circuit_breaker_open

# Identificar qual circuit breaker está aberto
kubectl logs -n ${ORCHESTRATION_NS} -l app=orchestrator-dynamic --tail=200 | grep -E "(circuit_breaker_state|circuit_breaker_open)"

# Verificar dependências downstream
kubectl get pods -n ${MONGODB_NS} -l app=mongodb
kubectl get pods -n ${KAFKA_NS} -l app=kafka
kubectl get pods -n ${REGISTRY_NS} -l app=service-registry

# Forçar reset do circuit breaker (se dependência recuperada)
kubectl rollout restart deployment/orchestrator-dynamic -n ${ORCHESTRATION_NS}

# Monitorar métricas de circuit breaker
curl -s "http://prometheus.${MONITORING_NS}:9090/api/v1/query?query=neural_hive_circuit_breaker_state" | jq
```

### High Memory Usage

```bash
# Check memory usage
kubectl top pods -n neural-hive-orchestration
kubectl top pods -n neural-hive-execution

# Check specific pod memory
kubectl top pod orchestrator-dynamic-xxx -n neural-hive-orchestration

# Increase memory limits (temporary)
kubectl patch deployment orchestrator-dynamic -n neural-hive-orchestration -p '{
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "name": "orchestrator",
          "resources": {
            "limits": {"memory": "4Gi"},
            "requests": {"memory": "2Gi"}
          }
        }]
      }
    }
  }
}'

# Restart pods to apply
kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration
```

### High CPU Usage

```bash
# Check CPU usage
kubectl top pods -n neural-hive-orchestration --sort-by=cpu

# Identify hot pods
kubectl top pods -n neural-hive-execution --sort-by=cpu

# Scale up to distribute load
kubectl scale deployment orchestrator-dynamic --replicas=5 -n neural-hive-orchestration
kubectl scale deployment worker-agents --replicas=10 -n neural-hive-execution

# Monitor after scaling
watch -n 5 'kubectl top pods -n neural-hive-orchestration'
```

### Pod Crash Loop

```bash
# Check pod status
kubectl get pods -n neural-hive-orchestration -l app=orchestrator-dynamic

# Get crash reason
kubectl describe pod orchestrator-dynamic-xxx -n neural-hive-orchestration | grep -A 20 "Last State:"

# Check recent logs
kubectl logs -n neural-hive-orchestration orchestrator-dynamic-xxx --previous --tail=100

# Check events
kubectl get events -n neural-hive-orchestration --sort-by='.lastTimestamp' | tail -20

# Force delete stuck pod
kubectl delete pod orchestrator-dynamic-xxx -n neural-hive-orchestration --force --grace-period=0
```

### Network Issues

```bash
# Test connectivity to MongoDB
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  nc -zv mongodb 27017

# Test connectivity to Kafka
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  nc -zv kafka 9092

# Test connectivity to Service Registry
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  nc -zv service-registry.neural-hive-registry 50051

# Check DNS resolution
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  nslookup mongodb

# Check network policies
kubectl get networkpolicies -n neural-hive-orchestration
```

---

## Rollback Procedures

### Rollback Deployment

```bash
# Check rollout history
kubectl rollout history deployment/orchestrator-dynamic -n neural-hive-orchestration

# Rollback to previous revision
kubectl rollout undo deployment/orchestrator-dynamic -n neural-hive-orchestration

# Rollback to specific revision
kubectl rollout undo deployment/orchestrator-dynamic -n neural-hive-orchestration --to-revision=3

# Verify rollback
kubectl rollout status deployment/orchestrator-dynamic -n neural-hive-orchestration
```

### Rollback Configuration

```bash
# Restore ConfigMap from backup
kubectl apply -f /path/to/backup/orchestrator-config.yaml -n neural-hive-orchestration

# Restart to apply
kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration
```

---

---

## Simulação de Incidentes

Para validação dos procedimentos deste runbook em ambiente de staging, utilize o script de simulação de incidentes:

```bash
# Executar simulação interativa
./scripts/validation/simulate-flow-c-incidents.sh

# Rollback de emergência
./scripts/validation/simulate-flow-c-incidents.sh --rollback
```

**Cenários disponíveis:**
1. Workers Indisponíveis (FlowCWorkersUnavailable)
2. Consumer Group Pausado (lag em Kafka)
3. Workflow Stuck (FlowCHighLatency)
4. Circuit Breaker Aberto (MongoDB)

**ATENÇÃO:** Executar apenas em ambiente de staging/desenvolvimento.

---

## References

- [Flow C Integration Guide](../PHASE2_FLOW_C_INTEGRATION.md)
- [Flow C Troubleshooting](./flow-c-troubleshooting.md)
- [Flow C Disaster Recovery](./flow-c-disaster-recovery.md)
- [Prometheus Alerts](../../monitoring/alerts/flow-c-integration-alerts.yaml)
- [Grafana Dashboard](../../monitoring/dashboards/fluxo-c-orquestracao.json)
- [Phase 2 Operations](./phase2-operations.md)
- [Script de Simulação de Incidentes](../../scripts/validation/simulate-flow-c-incidents.sh)
