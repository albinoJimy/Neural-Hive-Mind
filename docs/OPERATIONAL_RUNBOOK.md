# Operational Runbook
## Neural Hive-Mind - Phase 1

**Version**: 1.0
**Last Updated**: 2025-11-12
**Maintainer**: Neural Hive-Mind Team

---

## 📑 Table of Contents

1. [Quick Reference](#1-quick-reference)
2. [Infrastructure Troubleshooting](#2-infrastructure-troubleshooting)
3. [Service Troubleshooting](#3-service-troubleshooting)
4. [Connectivity Troubleshooting](#4-connectivity-troubleshooting)
5. [Performance Troubleshooting](#5-performance-troubleshooting)
6. [Data Troubleshooting](#6-data-troubleshooting)
7. [Observability Troubleshooting](#7-observability-troubleshooting)
8. [Governance Troubleshooting](#8-governance-troubleshooting)
9. [Common Scenarios](#9-common-scenarios)
10. [Maintenance Procedures](#10-maintenance-procedures)

---

## 1. Quick Reference

### Most Used Commands

**Pod Status**:
```bash
# All pods status
kubectl get pods -A | grep -E "(Running|Pending|Error|CrashLoop)"

# Specific namespace
kubectl get pods -n <namespace> -o wide

# Pod details
kubectl describe pod <pod-name> -n <namespace>

# Pod logs (live)
kubectl logs -f <pod-name> -n <namespace>

# Previous container logs (if crashed)
kubectl logs <pod-name> -n <namespace> --previous
```

**Health Checks**:
```bash
# Gateway health (REST)
kubectl port-forward -n gateway-intencoes svc/gateway-intencoes 8000:8000
curl http://localhost:8000/health

# Specialist health (gRPC)
kubectl port-forward -n specialist-business svc/specialist-business-grpc 50051:50051
grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check
```

**Resource Monitoring**:
```bash
# Node resources
kubectl top nodes

# Pod resources
kubectl top pods -A --sort-by=cpu
kubectl top pods -A --sort-by=memory

# Allocated resources
kubectl describe node <node-name> | grep -A 10 "Allocated resources"
```

**Quick Restarts**:
```bash
# Restart deployment
kubectl rollout restart deployment <deployment-name> -n <namespace>

# Delete pod (will recreate)
kubectl delete pod <pod-name> -n <namespace>

# Scale down and up
kubectl scale deployment <deployment-name> -n <namespace> --replicas=0
kubectl scale deployment <deployment-name> -n <namespace> --replicas=1
```

---

## 2. Infrastructure Troubleshooting

### 2.1 Kafka Issues

#### Symptom: Topic Not Found
**Error**: `UnknownTopicOrPartitionException`

**Diagnosis**:
```bash
# List all topics
kubectl exec -n kafka kafka-0 -- kafka-topics.sh \
  --bootstrap-server localhost:9092 --list

# Describe specific topic
kubectl exec -n kafka kafka-0 -- kafka-topics.sh \
  --bootstrap-server localhost:9092 --describe --topic <topic-name>
```

**Solution**:
```bash
# Create topic manually
kubectl exec -n kafka kafka-0 -- kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --topic <topic-name> \
  --partitions 3 --replication-factor 1

# Or via KafkaTopic CRD
cat <<EOF | kubectl apply -f -
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: <topic-name>
  namespace: kafka
  labels:
    strimzi.io/cluster: neural-hive-kafka
spec:
  partitions: 3
  replicas: 1
  config:
    retention.ms: 604800000
    segment.bytes: 1073741824
EOF
```

#### Symptom: Producer Cannot Connect
**Error**: `KafkaTimeoutError: Failed to send message`

**Diagnosis**:
```bash
# Check Kafka pod status
kubectl get pods -n kafka

# Test connectivity
kubectl run kafka-test --image=bitnami/kafka:latest --rm -it --restart=Never -- \
  kafka-console-producer.sh --bootstrap-server neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092 --topic test
```

**Solution**:
- Verify Kafka service exists: `kubectl get svc -n kafka`
- Check DNS resolution: `kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local`
- Verify bootstrap servers in application config

#### Symptom: Consumer Lag Growing
**Error**: Consumers not keeping up with producers

**Diagnosis**:
```bash
# Check consumer group lag
kubectl exec -n kafka kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group <consumer-group> --describe
```

**Solution**:
- Scale consumer pods: `kubectl scale deployment <name> -n <namespace> --replicas=<N>`
- Increase partition count (requires Kafka admin)
- Optimize consumer processing time

---

### 2.2 MongoDB Issues

#### Symptom: Authentication Failed
**Error**: `Command requires authentication`

**Diagnosis**:
```bash
# Check MongoDB URI in ConfigMap
kubectl get configmap -n <namespace> <service>-config -o yaml | grep MONGODB_URI

# Test authentication
kubectl exec -n mongodb-cluster -it mongodb-0 -- \
  mongosh "mongodb://root:local_dev_password@localhost:27017/?authSource=admin" \
  --eval "db.adminCommand('ping')"
```

**Solution**:
```yaml
# Correct MongoDB URI format:
mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin

# Update in values-local.yaml and redeploy
helm upgrade consensus-engine helm-charts/consensus-engine/ \
  -n consensus-engine \
  -f helm-charts/consensus-engine/values-local.yaml
```

#### Symptom: Connection Timeout
**Error**: `ServerSelectionTimeoutError`

**Diagnosis**:
```bash
# Check MongoDB pod
kubectl get pods -n mongodb-cluster

# Test network connectivity
kubectl run mongo-test --image=busybox --rm -it --restart=Never -- \
  nc -zv mongodb.mongodb-cluster.svc.cluster.local 27017
```

**Solution**:
- Verify MongoDB service: `kubectl get svc -n mongodb-cluster`
- Check MongoDB logs: `kubectl logs -n mongodb-cluster mongodb-0`
- Increase connection timeout in application config

---

### 2.3 Redis Issues

#### Symptom: Connection Refused
**Error**: `ConnectionRefusedError: [Errno 111] Connection refused`

**Diagnosis**:
```bash
# Check Redis pod
kubectl get pods -n redis-cluster

# Test Redis connectivity
kubectl run redis-test --image=redis:7.0 --rm -it --restart=Never -- \
  redis-cli -h redis.redis-cluster.svc.cluster.local -p 6379 PING
```

**Solution**:
```bash
# Verify Redis service
kubectl get svc -n redis-cluster

# Restart Redis if unhealthy
kubectl rollout restart deployment redis -n redis-cluster

# Check Redis configuration
kubectl logs -n redis-cluster <redis-pod-name>
```

#### Symptom: Keys Not Expiring
**Problem**: TTL not working, memory filling up

**Diagnosis**:
```bash
# Connect to Redis
kubectl exec -n redis-cluster -it <redis-pod> -- redis-cli

# Check key TTL
TTL pheromone:test-key

# Check memory usage
INFO memory
```

**Solution**:
```bash
# Manually set TTL if missing
EXPIRE pheromone:test-key 300

# Flush expired keys (if needed)
# WARNING: Use with caution
FLUSHDB
```

---

### 2.4 Neo4j Issues

#### Symptom: Bolt Connection Timeout
**Error**: `ServiceUnavailable: Unable to connect to bolt://neo4j:7687`

**Diagnosis**:
```bash
# Check Neo4j pod
kubectl get pods -n neo4j-cluster

# Test Bolt port
kubectl run neo4j-test --image=busybox --rm -it --restart=Never -- \
  nc -zv neo4j.neo4j-cluster.svc.cluster.local 7687
```

**Solution**:
```bash
# Port-forward to test locally
kubectl port-forward -n neo4j-cluster svc/neo4j 7687:7687

# Check credentials (usually neo4j/neo4j for dev)
# Update in application config if needed
```

---

## 3. Service Troubleshooting

### 3.1 Gateway de Intenções

#### Symptom: Pod Not Starting (ImagePullBackOff)
**Diagnosis**:
```bash
kubectl describe pod -n gateway-intencoes -l app.kubernetes.io/name=gateway-intencoes | grep -A 5 "Events:"
```

**Solution**:
```bash
eval $(minikube docker-env)
cd /jimy/Neural-Hive-Mind
docker build -f services/gateway-intencoes/Dockerfile -t neural-hive-mind/gateway-intencoes:1.0.0 .
kubectl delete pod -n gateway-intencoes -l app.kubernetes.io/name=gateway-intencoes
```

#### Symptom: Health Check Fails
**Error**: `/health` returns 503 or timeout

**Diagnosis**:
```bash
kubectl logs -n gateway-intencoes -l app.kubernetes.io/name=gateway-intencoes --tail=50
```

**Solution**:
- Check Kafka connectivity
- Check Redis connectivity
- Verify all dependencies are Running

#### Symptom: Classification Incorrect
**Problem**: 80% of intents classified as "technical"

**Root Cause**: NLU model needs retraining

**Solution** (Long-term):
- Collect training data from production
- Retrain spaCy model with domain-specific data
- Update model in application

---

### 3.2 Semantic Translation Engine

#### Symptom: Not Consuming from Kafka
**Error**: No logs showing message consumption

**Diagnosis**:
```bash
# Check if pod is running
kubectl get pods -n semantic-translation-engine

# Check logs
kubectl logs -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine --tail=100

# Check consumer group
kubectl exec -n kafka kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group semantic-translation-engine --describe
```

**Solution**:
```bash
# Verify Kafka topic exists
kubectl exec -n kafka kafka-0 -- kafka-topics.sh \
  --bootstrap-server localhost:9092 --list | grep intentions

# Restart consumer
kubectl rollout restart deployment semantic-translation-engine -n semantic-translation-engine
```

#### Symptom: Plans Not Generated
**Error**: Consumer active but no plans produced

**Diagnosis**:
```bash
# Check for errors in logs
kubectl logs -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine | grep -i error

# Check Neo4j connectivity
kubectl logs -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine | grep -i neo4j
```

**Solution**:
- Verify Neo4j is accessible (see section 2.4)
- Check plan generation logic for exceptions
- Verify output topic (`plans.ready`) exists

---

### 3.3 Specialists

#### Symptom: TypeError in Timestamp Protobuf (RESOLVED v1.0.7)
**Error**: `TypeError: Timestamp() takes no keyword arguments`

**Diagnosis**:
```bash
kubectl logs -n specialist-business -l app.kubernetes.io/name=specialist-business | grep TypeError
```

**Solution**: Ensure v1.0.7 or later is deployed
```bash
# Verify version
kubectl get deployment -n specialist-business specialist-business -o jsonpath='{.spec.template.spec.containers[0].image}'

# If not v1.0.7, rebuild and redeploy
docker build -f services/specialist-business/Dockerfile -t neural-hive-mind/specialist-business:1.0.7 .
helm upgrade specialist-business helm-charts/specialist-business/ -n specialist-business -f helm-charts/specialist-business/values-local.yaml
```

#### Symptom: gRPC Server Not Starting
**Error**: `Failed to bind to port 50051`

**Diagnosis**:
```bash
kubectl logs -n specialist-business -l app.kubernetes.io/name=specialist-business | grep "port 50051"
```

**Solution**:
- Check if port is already in use (unlikely in K8s)
- Verify Dockerfile exposes port 50051
- Check service definition has port 50051

#### Symptom: MLflow Not Accessible (Using Fallback)
**Warning**: `MLflow unavailable, using heuristic fallback`

**This is expected** in dev environment. Fallback heuristic is functional.

**Solution** (If MLflow needed):
```bash
# Scale up MLflow
kubectl scale deployment mlflow -n mlflow --replicas=1

# Wait for pod to be ready
kubectl wait --for=condition=ready pod -n mlflow -l app=mlflow --timeout=60s
```

---

### 3.4 Consensus Engine

#### Symptom: CrashLoopBackOff (MongoDB Auth Issue)
**Error**: Silent crash, no logs

**Diagnosis**:
```bash
kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine --previous
kubectl describe pod -n consensus-engine -l app.kubernetes.io/name=consensus-engine
```

**Solution**:
```bash
# Verify MongoDB URI includes auth
kubectl get configmap -n consensus-engine consensus-engine-config -o yaml | grep MONGODB_URI

# Should be:
# mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin

# If incorrect, update values-local.yaml and redeploy
helm upgrade consensus-engine helm-charts/consensus-engine/ \
  -n consensus-engine \
  -f helm-charts/consensus-engine/values-local.yaml
```

#### Symptom: Specialists Not Invoked
**Error**: `gRPC timeout calling specialist`

**Diagnosis**:
```bash
# Check specialist endpoints in ConfigMap
kubectl get configmap -n consensus-engine consensus-engine-config -o yaml | grep SPECIALIST_.*_ENDPOINT

# Test specialist connectivity
kubectl run grpc-test --image=fullstorydev/grpcurl --rm -it --restart=Never -- \
  -plaintext specialist-business.specialist-business.svc.cluster.local:50051 grpc.health.v1.Health/Check
```

**Solution**:
- Verify all specialist pods are Running
- Ensure endpoints follow format: `<service>.<namespace>.svc.cluster.local:50051`
- Check consensus engine requires minimum 3/5 specialists available

---

### 3.5 Memory Layer API

#### Symptom: Layers Disconnected
**Error**: `/ready` returns false for memory layers

**Diagnosis**:
```bash
kubectl port-forward -n memory-layer-api svc/memory-layer-api 8000:8000
curl http://localhost:8000/ready | jq .
```

**Solution**:
- Check MongoDB (WARM): See section 2.2
- Check Redis (HOT): See section 2.3
- Check Neo4j (SEMANTIC): See section 2.4
- Check ClickHouse (COLD): Similar to Neo4j

#### Symptom: CronJobs in ContainerCreating
**Problem**: Sync, retention, or quality CronJobs stuck

**Diagnosis**:
```bash
kubectl get cronjobs -n memory-layer-api
kubectl describe cronjob memory-sync -n memory-layer-api
```

**Solution**:
```bash
# Usually resolves when Memory Layer API pod is healthy
# If persists, delete and let recreate
kubectl delete cronjob memory-sync -n memory-layer-api
helm upgrade memory-layer-api helm-charts/memory-layer-api/ -n memory-layer-api -f helm-charts/memory-layer-api/values-local.yaml
```

---

## 4. Connectivity Troubleshooting

### DNS Resolution Failures

**Symptom**: `Name or service not known`

**Diagnosis**:
```bash
# Test DNS resolution
kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup <service>.<namespace>.svc.cluster.local

# Check CoreDNS
kubectl get pods -n kube-system -l k8s-app=kube-dns
```

**Solution**:
```bash
# Restart CoreDNS if unhealthy
kubectl rollout restart deployment coredns -n kube-system
```

### Service Discovery Issues

**Symptom**: Services cannot find each other

**Diagnosis**:
```bash
# List all services
kubectl get svc -A

# Verify ClusterIP assigned
kubectl get svc <service-name> -n <namespace> -o jsonpath='{.spec.clusterIP}'
```

**Solution**:
- Ensure service exists: `kubectl get svc <name> -n <namespace>`
- Check service selector matches pod labels
- Verify service port matches container port

---

## 5. Performance Troubleshooting

### CPU Throttling (94%+ Utilization)

**Symptom**: Pods in Pending, slow performance

**Diagnosis**:
```bash
kubectl top nodes
kubectl describe node <node-name> | grep -A 10 "Allocated resources"
```

**Solution**:
```bash
# Option 1: Scale down non-critical services
kubectl scale deployment mlflow -n mlflow --replicas=0
kubectl scale deployment redis -n redis-cluster --replicas=0

# Option 2: Reduce resource requests
# Edit values-local.yaml, reduce CPU requests by 20%
helm upgrade <service> helm-charts/<service>/ -n <namespace> -f helm-charts/<service>/values-local.yaml

# Option 3: Add cluster nodes (production)
```

### Memory Leaks

**Symptom**: Memory usage growing over time

**Diagnosis**:
```bash
kubectl top pods -n <namespace> --sort-by=memory
```

**Solution**:
```bash
# Restart affected pod
kubectl delete pod <pod-name> -n <namespace>

# Long-term: Profile application, fix memory leaks in code
```

### High Latency (>1s)

**Symptom**: Slow response times

**Diagnosis**:
- Check Prometheus metrics (if available)
- Review application logs for slow queries
- Check database connection pool saturation

**Solution**:
- Optimize database queries
- Increase connection pool size
- Add caching layers
- Scale horizontally (more replicas)

---

## 6. Data Troubleshooting

### Ledger Integrity Failures

**Symptom**: Hash mismatch detected

**Diagnosis**:
```bash
# Connect to MongoDB
kubectl exec -n mongodb-cluster -it mongodb-0 -- mongosh "mongodb://root:local_dev_password@localhost:27017/?authSource=admin"

use neural_hive
db.cognitive_ledger.find({ decision_hash: { $exists: true } }).limit(10)
```

**Solution**:
- Investigate tampering (security incident)
- Restore from backup if data corrupted
- Review access controls

### Explainability Tokens Missing

**Symptom**: Decisions without explainability_token

**Diagnosis**:
```bash
# Query decisions without tokens
db.cognitive_ledger.find({ explainability_token: { $exists: false } }).count()
```

**Solution**:
- Check Consensus Engine logs for errors
- Verify explainability service is operational
- Backfill tokens if necessary (manual process)

---

## 7. Observability Troubleshooting

### Prometheus Targets Down

**Symptom**: ServiceMonitors not discovered

**Diagnosis**:
```bash
# Check Prometheus pod
kubectl get pods -n neural-hive-observability -l app.kubernetes.io/name=prometheus

# Check ServiceMonitors
kubectl get servicemonitors -A
```

**Solution**:
```bash
# Restart Prometheus
kubectl rollout restart statefulset prometheus -n neural-hive-observability

# Verify service labels match ServiceMonitor selector
```

### Grafana Dashboards No Data

**Symptom**: Dashboards empty

**Diagnosis**:
- Check Prometheus datasource configured in Grafana
- Verify metrics being scraped: Prometheus UI → Targets

**Solution**:
```bash
# Import dashboards manually
kubectl port-forward -n neural-hive-observability svc/grafana 3000:3000
# Access http://localhost:3000, import JSON files from monitoring/dashboards/
```

---

## 8. Governance Troubleshooting

### OPA Gatekeeper Webhook Not Responding

**Symptom**: `admission webhook denied the request` on all operations

**Diagnosis**:
```bash
kubectl get pods -n gatekeeper-system
kubectl logs -n gatekeeper-system -l app=gatekeeper
```

**Solution**:
```bash
# Restart Gatekeeper
kubectl rollout restart deployment gatekeeper-controller-manager -n gatekeeper-system
kubectl rollout restart deployment gatekeeper-audit -n gatekeeper-system
```

---

## 9. Common Scenarios

### Scenario 1: System Not Processing Intents

**Symptoms**: No plans generated, no decisions made

**Diagnosis Steps**:
1. Check Gateway health: `kubectl logs -n gateway-intencoes -l app.kubernetes.io/name=gateway-intencoes --tail=20`
2. Verify Kafka topics exist: See section 2.1
3. Check STE consuming: See section 3.2
4. Verify specialists running: `kubectl get pods -A | grep specialist`
5. Check consensus engine logs: `kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine --tail=50`

**Resolution**:
- Fix any failing component identified above
- Ensure complete flow: Gateway → Kafka → STE → Kafka → Consensus → Specialists

---

### Scenario 2: Cluster Out of Resources

**Symptoms**: Pods Pending, evictions

**Diagnosis**:
```bash
kubectl get pods -A | grep Pending
kubectl top nodes
kubectl describe node <node> | grep -A 10 "Allocated resources"
```

**Resolution**:
1. Scale down non-critical: MLflow, Redis (if not used), ClickHouse (optional)
2. Reduce resource requests in values-local.yaml
3. Add cluster nodes (if possible)
4. Delete unused pods/deployments

---

### Scenario 3: Testes E2E Falhando

**Symptoms**: Test script reports failures

**Diagnosis**:
```bash
# Run pre-validation first
./tests/phase1-pre-test-validation.sh

# Check output for specific failures
```

**Resolution**:
- Fix infrastructure issues first (Kafka, MongoDB, Redis)
- Ensure all services are Running
- Verify health checks pass
- Then run E2E test: `./tests/phase1-end-to-end-test.sh`

---

## 10. Maintenance Procedures

### Graceful Service Restart

```bash
# Rolling restart (zero downtime)
kubectl rollout restart deployment <deployment-name> -n <namespace>

# Wait for completion
kubectl rollout status deployment <deployment-name> -n <namespace>
```

### Hard Restart (If Needed)

```bash
# Delete all pods (will recreate)
kubectl delete pods -n <namespace> -l app.kubernetes.io/name=<service>
```

### Scaling Services

```bash
# Scale up
kubectl scale deployment <name> -n <namespace> --replicas=3

# Scale down
kubectl scale deployment <name> -n <namespace> --replicas=1

# Scale to zero (disable)
kubectl scale deployment <name> -n <namespace> --replicas=0
```

### Backup & Restore

**MongoDB Backup**:
```bash
kubectl exec -n mongodb-cluster mongodb-0 -- mongodump --uri="mongodb://root:local_dev_password@localhost:27017/?authSource=admin" --out=/tmp/backup

kubectl cp mongodb-cluster/mongodb-0:/tmp/backup ./mongodb-backup-$(date +%Y%m%d)
```

**Redis Backup**:
```bash
kubectl exec -n redis-cluster <redis-pod> -- redis-cli BGSAVE
kubectl exec -n redis-cluster <redis-pod> -- cat /data/dump.rdb > redis-backup-$(date +%Y%m%d).rdb
```

### Version Upgrades

```bash
# Build new version
docker build -f services/<service>/Dockerfile -t neural-hive-mind/<service>:<new-version> .

# Update Helm chart
helm upgrade <service> helm-charts/<service>/ \
  -n <namespace> \
  -f helm-charts/<service>/values-local.yaml \
  --set image.tag=<new-version>

# Verify rollout
kubectl rollout status deployment <service> -n <namespace>
```

---

## 📞 Escalation & Support

**Priority Levels**:
- **P0 (Critical)**: System down, data loss
- **P1 (High)**: Major feature broken, degraded performance
- **P2 (Medium)**: Minor feature broken, workaround exists
- **P3 (Low)**: Cosmetic issues, enhancement requests

**Escalation Path**:
1. Check this runbook first
2. Review service-specific troubleshooting guides in `docs/`
3. Check GitHub issues: https://github.com/anthropics/neural-hive-mind/issues (if applicable)
4. Contact DevOps/SRE team

**Useful Links**:
- [Phase 1 Testing Guide](PHASE1_TESTING_GUIDE.md)
- [Phase 1 Executive Report](PHASE1_EXECUTIVE_REPORT.md)
- [Kubernetes Documentation](https://kubernetes.io/docs/)

---

**Runbook Version**: 1.0
**Last Updated**: 2025-11-12
**Maintained by**: Neural Hive-Mind Team
