# Flow C Disaster Recovery Playbook

## Overview

Procedimentos de disaster recovery específicos para Flow C - Orquestração de Execução Adaptativa. Este playbook cobre cenários de falha crítica, procedimentos de backup/restore e comunicação durante incidentes.

---

## Recovery Scenarios

### 1. MongoDB Orchestration Cluster Failure

**RTO (Recovery Time Objective):** 30 minutes
**RPO (Recovery Point Objective):** 1 hour (backup frequency)

#### Pre-Recovery Checklist

- [ ] Identify last successful backup
- [ ] Verify backup integrity
- [ ] Notify stakeholders via #neural-hive-incidents
- [ ] Create incident in PagerDuty
- [ ] Stop Flow C services to prevent data corruption

#### Recovery Steps

**1. Stop Flow C services:**

```bash
# Stop in reverse dependency order
kubectl scale deployment worker-agents --replicas=0 -n neural-hive-execution
kubectl scale deployment orchestrator-dynamic --replicas=0 -n neural-hive-orchestration
kubectl scale deployment execution-ticket-service --replicas=0 -n neural-hive-orchestration

# Verify all pods terminated
kubectl get pods -n neural-hive-orchestration -l app=orchestrator-dynamic
kubectl get pods -n neural-hive-execution -l app=worker-agents
```

**2. Identify last backup:**

```bash
# List backups in S3
aws s3 ls s3://neural-hive-backups-prod/mongodb/orchestration/ --recursive | sort | tail -10

# Verify backup integrity
aws s3 cp s3://neural-hive-backups-prod/mongodb/orchestration/backup-2024-01-15.tar.gz /tmp/
tar -tzf /tmp/backup-2024-01-15.tar.gz | head -20

# Check backup metadata
aws s3 cp s3://neural-hive-backups-prod/mongodb/orchestration/backup-2024-01-15.metadata.json /tmp/
cat /tmp/backup-2024-01-15.metadata.json
```

**3. Restore MongoDB:**

```bash
# Download backup
aws s3 cp s3://neural-hive-backups-prod/mongodb/orchestration/backup-2024-01-15.tar.gz /tmp/

# Extract
mkdir -p /tmp/mongodb-restore
tar -xzf /tmp/backup-2024-01-15.tar.gz -C /tmp/mongodb-restore/

# Copy to MongoDB pod
kubectl cp /tmp/mongodb-restore neural-hive-orchestration/mongodb-0:/tmp/restore

# Restore using mongorestore
kubectl exec -n neural-hive-orchestration mongodb-0 -- \
  mongorestore --uri mongodb://mongodb:27017 --drop /tmp/restore/

# Verify restoration
kubectl exec -n neural-hive-orchestration mongodb-0 -- \
  mongosh mongodb://mongodb:27017/neural_hive --eval 'db.execution_tickets.countDocuments({})'
```

**4. Rebuild indexes:**

```bash
kubectl exec -n neural-hive-orchestration mongodb-0 -- \
  mongosh mongodb://mongodb:27017/neural_hive --eval '
    // Execution tickets indexes
    db.execution_tickets.createIndex({ticket_id: 1}, {unique: true});
    db.execution_tickets.createIndex({plan_id: 1});
    db.execution_tickets.createIndex({intent_id: 1});
    db.execution_tickets.createIndex({decision_id: 1});
    db.execution_tickets.createIndex({status: 1});
    db.execution_tickets.createIndex({plan_id: 1, created_at: -1});
    db.execution_tickets.createIndex({created_at: 1}, {expireAfterSeconds: 2592000}); // 30 days TTL

    // Validation audit indexes
    db.validation_audit.createIndex({workflow_id: 1});
    db.validation_audit.createIndex({timestamp: -1});
    db.validation_audit.createIndex({decision_id: 1});

    // Workflow results indexes
    db.workflow_results.createIndex({workflow_id: 1}, {unique: true});
    db.workflow_results.createIndex({plan_id: 1});
    db.workflow_results.createIndex({completed_at: -1});

    print("Indexes rebuilt successfully");
  '
```

**5. Validate data integrity:**

```bash
# Verify collections exist
kubectl exec -n neural-hive-orchestration mongodb-0 -- \
  mongosh mongodb://mongodb:27017/neural_hive --eval 'db.getCollectionNames()'

# Verify indexes
kubectl exec -n neural-hive-orchestration mongodb-0 -- \
  mongosh mongodb://mongodb:27017/neural_hive --eval 'db.execution_tickets.getIndexes()'

# Verify document counts
kubectl exec -n neural-hive-orchestration mongodb-0 -- \
  mongosh mongodb://mongodb:27017/neural_hive --eval '
    print("execution_tickets: " + db.execution_tickets.countDocuments({}));
    print("validation_audit: " + db.validation_audit.countDocuments({}));
    print("workflow_results: " + db.workflow_results.countDocuments({}));
  '

# Sample data validation
kubectl exec -n neural-hive-orchestration mongodb-0 -- \
  mongosh mongodb://mongodb:27017/neural_hive --eval 'db.execution_tickets.find().limit(3).pretty()'
```

**6. Restart Flow C services:**

```bash
# Start in dependency order
kubectl scale deployment execution-ticket-service --replicas=2 -n neural-hive-orchestration
kubectl scale deployment orchestrator-dynamic --replicas=2 -n neural-hive-orchestration
kubectl scale deployment worker-agents --replicas=3 -n neural-hive-execution

# Wait for readiness
kubectl wait --for=condition=ready pod -l app=execution-ticket-service -n neural-hive-orchestration --timeout=120s
kubectl wait --for=condition=ready pod -l app=orchestrator-dynamic -n neural-hive-orchestration --timeout=120s
kubectl wait --for=condition=ready pod -l app=worker-agents -n neural-hive-execution --timeout=120s
```

#### Post-Recovery Validation

```bash
# Verify services healthy
kubectl get pods -n neural-hive-orchestration
kubectl get pods -n neural-hive-execution

# Verify MongoDB connectivity
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python -c "from pymongo import MongoClient; print(MongoClient('mongodb://mongodb:27017').server_info())"

# Run smoke test
./tests/phase2-flow-c-integration-test.sh --smoke-test

# Verify metrics
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=up{job=\"orchestrator-dynamic\"}" | jq
```

---

### 2. Kafka Cluster Failure

**RTO:** 45 minutes
**RPO:** 5 minutes (MirrorMaker replication lag)

#### Pre-Recovery Checklist

- [ ] Identify last successful backup
- [ ] Verify MirrorMaker backup or tiered storage
- [ ] Notify stakeholders
- [ ] Document consumer offsets

#### Recovery Steps

**1. Stop consumers:**

```bash
kubectl scale deployment orchestrator-dynamic --replicas=0 -n neural-hive-orchestration
kubectl scale deployment worker-agents --replicas=0 -n neural-hive-execution

# Verify consumers stopped
kubectl get pods -n neural-hive-orchestration -l app=orchestrator-dynamic
```

**2. Document current consumer offsets (if available):**

```bash
# Export offsets before recovery
kubectl exec -n neural-hive-messaging kafka-0 -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --all-groups > /tmp/offsets-pre-recovery.txt 2>/dev/null || true

# Save to S3 for reference
aws s3 cp /tmp/offsets-pre-recovery.txt s3://neural-hive-backups-prod/kafka/recovery/offsets-$(date +%Y%m%d-%H%M).txt
```

**3. Restore Kafka from backup:**

```bash
# Option A: Restore from MirrorMaker backup cluster
kubectl exec -n neural-hive-messaging-backup kafka-mirror-0 -- \
  kafka-mirror-maker.sh --consumer.config /etc/kafka/consumer.properties \
  --producer.config /etc/kafka/producer.properties \
  --whitelist "plans.consensus|execution.tickets|execution.results|telemetry-flow-c"

# Option B: Restore from tiered storage (if enabled)
kubectl exec -n neural-hive-messaging kafka-0 -- \
  kafka-log-dirs.sh --bootstrap-server localhost:9092 --describe --topic-list plans.consensus,execution.tickets,execution.results,telemetry-flow-c

# Option C: Recreate topics (data loss scenario)
kubectl exec -n neural-hive-messaging kafka-0 -- bash -c '
  kafka-topics.sh --bootstrap-server localhost:9092 --create --topic plans.consensus --partitions 6 --replication-factor 3 --if-not-exists
  kafka-topics.sh --bootstrap-server localhost:9092 --create --topic execution.tickets --partitions 12 --replication-factor 3 --if-not-exists
  kafka-topics.sh --bootstrap-server localhost:9092 --create --topic execution.results --partitions 6 --replication-factor 3 --if-not-exists
  kafka-topics.sh --bootstrap-server localhost:9092 --create --topic telemetry-flow-c --partitions 6 --replication-factor 3 --if-not-exists
'
```

**4. Reset consumer offsets:**

```bash
# Reset to last checkpoint (if known)
kubectl exec -n neural-hive-messaging kafka-0 -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --group orchestrator-consumers --reset-offsets --to-datetime 2024-01-15T10:00:00.000 --topic plans.consensus --execute

kubectl exec -n neural-hive-messaging kafka-0 -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --group worker-consumers --reset-offsets --to-datetime 2024-01-15T10:00:00.000 --topic execution.tickets --execute

# Or reset to latest (skip lost messages)
kubectl exec -n neural-hive-messaging kafka-0 -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --group orchestrator-consumers --reset-offsets --to-latest --topic plans.consensus --execute
```

**5. Verify topics:**

```bash
# List topics
kubectl exec -n neural-hive-messaging kafka-0 -- \
  kafka-topics.sh --bootstrap-server localhost:9092 --list | grep -E "(plans.consensus|execution.tickets|execution.results|telemetry-flow-c)"

# Describe topics
kubectl exec -n neural-hive-messaging kafka-0 -- \
  kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic plans.consensus

kubectl exec -n neural-hive-messaging kafka-0 -- \
  kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic execution.tickets
```

**6. Restart consumers:**

```bash
kubectl scale deployment orchestrator-dynamic --replicas=2 -n neural-hive-orchestration
kubectl scale deployment worker-agents --replicas=3 -n neural-hive-execution

# Wait for readiness
kubectl wait --for=condition=ready pod -l app=orchestrator-dynamic -n neural-hive-orchestration --timeout=120s
kubectl wait --for=condition=ready pod -l app=worker-agents -n neural-hive-execution --timeout=120s
```

**7. Monitor lag:**

```bash
# Monitor consumer lag
watch -n 5 'kubectl exec -n neural-hive-messaging kafka-0 -- kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group orchestrator-consumers'
```

#### Post-Recovery Validation

```bash
# Verify topics exist
kubectl exec -n neural-hive-messaging kafka-0 -- \
  kafka-topics.sh --bootstrap-server localhost:9092 --list | grep -E "(plans.consensus|execution.tickets|execution.results|telemetry-flow-c)"

# Verify consumers consuming
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=50 | grep "message_consumed"

# Verify no lag
kubectl exec -n neural-hive-messaging kafka-0 -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group orchestrator-consumers | grep LAG

# Test message flow
kubectl exec -n neural-hive-messaging kafka-0 -- \
  kafka-console-producer.sh --bootstrap-server localhost:9092 --topic execution.tickets <<< '{"test": "recovery-validation"}'
```

---

### 3. Temporal Workflow State Loss

**RTO:** 20 minutes
**RPO:** 1 hour (backup frequency)

#### Pre-Recovery Checklist

- [ ] Identify affected workflows
- [ ] Verify PostgreSQL Temporal backup
- [ ] Document workflow IDs
- [ ] Notify stakeholders

#### Recovery Steps

**1. Stop Temporal clients:**

```bash
kubectl scale deployment orchestrator-dynamic --replicas=0 -n neural-hive-orchestration

# Verify stopped
kubectl get pods -n neural-hive-orchestration -l app=orchestrator-dynamic
```

**2. Stop Temporal frontend:**

```bash
kubectl scale deployment temporal-frontend --replicas=0 -n temporal

# Verify stopped
kubectl get pods -n temporal -l app=temporal-frontend
```

**3. Restore PostgreSQL Temporal:**

```bash
# Identify last backup
aws s3 ls s3://neural-hive-backups-prod/temporal/backups/ | sort | tail -5

# Download backup
aws s3 cp s3://neural-hive-backups-prod/temporal/backups/backup-2024-01-15.sql.gz /tmp/

# Decompress
gunzip /tmp/backup-2024-01-15.sql.gz

# Copy to PostgreSQL pod
kubectl cp /tmp/backup-2024-01-15.sql temporal/postgresql-temporal-0:/tmp/

# Restore (this will drop existing data)
kubectl exec -n temporal postgresql-temporal-0 -- bash -c '
  psql -U temporal -d temporal -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''temporal'\'' AND pid <> pg_backend_pid();"
  dropdb -U temporal temporal --if-exists
  createdb -U temporal temporal
  psql -U temporal -d temporal < /tmp/backup-2024-01-15.sql
'
```

**4. Optional: Point-in-time recovery:**

```bash
# If WAL archiving is enabled
aws s3 cp s3://neural-hive-backups-prod/temporal/wal/ /tmp/wal/ --recursive

# Configure recovery in postgresql.conf
kubectl exec -n temporal postgresql-temporal-0 -- bash -c '
  echo "restore_command = '\''cp /tmp/wal/%f %p'\''" >> /var/lib/postgresql/data/postgresql.conf
  echo "recovery_target_time = '\''2024-01-15 10:30:00'\''" >> /var/lib/postgresql/data/postgresql.conf
  touch /var/lib/postgresql/data/recovery.signal
'

# Restart PostgreSQL
kubectl rollout restart statefulset/postgresql-temporal -n temporal
```

**5. Restart Temporal:**

```bash
kubectl scale deployment temporal-frontend --replicas=3 -n temporal
kubectl wait --for=condition=ready pod -l app=temporal-frontend -n temporal --timeout=120s

# Verify Temporal is healthy
kubectl exec -n temporal deployment/temporal-frontend -- tctl cluster health
```

**6. Verify workflows:**

```bash
# Restart orchestrator
kubectl scale deployment orchestrator-dynamic --replicas=2 -n neural-hive-orchestration
kubectl wait --for=condition=ready pod -l app=orchestrator-dynamic -n neural-hive-orchestration --timeout=120s

# List workflows
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  temporal workflow list --namespace default --limit 10

# Verify workflow state
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  temporal workflow describe --workflow-id flow-c-abc-123
```

**7. Restart stuck workflows (if needed):**

```bash
# Identify workflows that need restart
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  temporal workflow list --namespace default --query 'ExecutionStatus="Running"'

# Cancel and retry if necessary
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  temporal workflow cancel --workflow-id flow-c-abc-123 --reason "Recovery - workflow state inconsistent"

# Start retry workflow
# Note: Will need to recreate input from MongoDB execution_tickets
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  mongosh mongodb://mongodb:27017/neural_hive --eval 'db.execution_tickets.findOne({workflow_id: "flow-c-abc-123"})' > /tmp/workflow-input.json

kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  temporal workflow start --workflow-id flow-c-abc-123-retry --type OrchestrationWorkflow --task-queue orchestration-tasks --input @/tmp/workflow-input.json
```

#### Post-Recovery Validation

```bash
# Verify Temporal healthy
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  temporal workflow list --namespace default --limit 1

# Run smoke test workflow
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  temporal workflow start --workflow-id smoke-test-$(date +%s) --type OrchestrationWorkflow --task-queue orchestration-tasks --input '{"test": true}'

# Verify metrics
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=temporal_workflow_completed_total" | jq
```

---

### 4. Redis Cache Loss

**RTO:** 5 minutes
**RPO:** Acceptable (cache data, not critical)

#### Pre-Recovery Checklist

- [ ] Verify Redis persistence (AOF/RDB) status
- [ ] Document impact (idempotency, cache, pheromones)
- [ ] Notify stakeholders

#### Recovery Steps

**1. Verify Redis status:**

```bash
kubectl get pods -n neural-hive-orchestration | grep redis
kubectl logs -n neural-hive-orchestration redis-0 --tail=100
```

**2. Restore from persistence (if enabled):**

```bash
# Check if AOF/RDB exists
kubectl exec -n neural-hive-orchestration redis-0 -- ls -lh /data/

# If dump.rdb or appendonly.aof exists:
# Restart Redis to load from disk
kubectl rollout restart statefulset/redis -n neural-hive-orchestration

# Wait for Redis
kubectl wait --for=condition=ready pod -l app=redis -n neural-hive-orchestration --timeout=120s

# Verify data loaded
kubectl exec -n neural-hive-orchestration redis-0 -- redis-cli DBSIZE
```

**3. If no persistence (accept data loss):**

```bash
# Redis cache is fail-open, system continues without it
# Impact:
# - Idempotency keys will be rebuilt (possible duplicate processing)
# - Pheromone cache will be rebuilt
# - Telemetry buffer will be rebuilt

# Restart Redis to clear any corrupted state
kubectl rollout restart statefulset/redis -n neural-hive-orchestration

# Wait for Redis
kubectl wait --for=condition=ready pod -l app=redis -n neural-hive-orchestration --timeout=120s
```

**4. Restart dependent services:**

```bash
# Restart to clear circuit breakers and reconnect
kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration
kubectl rollout restart deployment/worker-agents -n neural-hive-execution

# Wait for services
kubectl wait --for=condition=ready pod -l app=orchestrator-dynamic -n neural-hive-orchestration --timeout=120s
kubectl wait --for=condition=ready pod -l app=worker-agents -n neural-hive-execution --timeout=120s
```

#### Post-Recovery Validation

```bash
# Verify Redis connectivity
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  redis-cli -h redis -p 6379 PING

# Verify idempotency working
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=50 | grep "idempotency"

# Verify cache rebuilding
kubectl exec -n neural-hive-orchestration redis-0 -- redis-cli DBSIZE

# Monitor over time
watch -n 30 'kubectl exec -n neural-hive-orchestration redis-0 -- redis-cli DBSIZE'
```

---

### 5. Complete Flow C Outage

**RTO:** 60 minutes
**RPO:** 1 hour (worst case across all components)

#### Pre-Recovery Checklist

- [ ] Identify root cause
- [ ] Verify all backups available
- [ ] Notify all stakeholders (P1 incident)
- [ ] Assemble incident response team
- [ ] Prepare emergency deploy script

#### Recovery Steps

**1. Execute emergency deploy:**

```bash
# Run emergency deploy script
./scripts/deploy/deploy-phase2-emergency.sh

# Or manually:
# Stop all services first
kubectl scale deployment worker-agents --replicas=0 -n neural-hive-execution
kubectl scale deployment orchestrator-dynamic --replicas=0 -n neural-hive-orchestration
kubectl scale deployment execution-ticket-service --replicas=0 -n neural-hive-orchestration
kubectl scale deployment service-registry --replicas=0 -n neural-hive-registry
```

**2. Restore databases in parallel:**

```bash
# Terminal 1: MongoDB
./scripts/maintenance/restore-mongodb-orchestration.sh &
MONGO_PID=$!

# Terminal 2: PostgreSQL Temporal
./scripts/maintenance/restore-postgres-temporal.sh &
TEMPORAL_PID=$!

# Terminal 3: Kafka topics
./scripts/maintenance/restore-kafka-topics.sh &
KAFKA_PID=$!

# Wait for all
wait $MONGO_PID $TEMPORAL_PID $KAFKA_PID

echo "All databases restored"
```

**3. Restore Redis (if needed):**

```bash
kubectl rollout restart statefulset/redis -n neural-hive-orchestration
kubectl wait --for=condition=ready pod -l app=redis -n neural-hive-orchestration --timeout=120s
```

**4. Deploy services in dependency order:**

```bash
# 1. Service Registry (no dependencies within Flow C)
kubectl apply -f k8s/service-registry/
kubectl wait --for=condition=ready pod -l app=service-registry -n neural-hive-registry --timeout=120s

# 2. Execution Ticket Service
kubectl apply -f k8s/execution-ticket-service/
kubectl wait --for=condition=ready pod -l app=execution-ticket-service -n neural-hive-orchestration --timeout=120s

# 3. Orchestrator Dynamic
kubectl apply -f k8s/orchestrator-dynamic/
kubectl wait --for=condition=ready pod -l app=orchestrator-dynamic -n neural-hive-orchestration --timeout=120s

# 4. Worker Agents
kubectl apply -f k8s/worker-agents/
kubectl wait --for=condition=ready pod -l app=worker-agents -n neural-hive-execution --timeout=120s
```

**5. Run E2E validation:**

```bash
./tests/phase2-end-to-end-test.sh

# Or manual validation
# Test MongoDB
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python -c "from pymongo import MongoClient; print(MongoClient('mongodb://mongodb:27017').server_info())"

# Test Kafka
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  kafka-console-consumer.sh --bootstrap-server kafka:9092 --topic plans.consensus --max-messages 1 --timeout-ms 5000

# Test Temporal
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  temporal workflow list --namespace default --limit 1

# Test Service Registry
kubectl exec -n neural-hive-registry deployment/service-registry -- \
  grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check
```

**6. Verify alerts clear:**

```bash
# Check Alertmanager
curl -s http://alertmanager.monitoring:9093/api/v2/alerts | jq '.[] | select(.labels.component == "flow-c")'

# Verify circuit breakers closed
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=100 | grep "circuit_breaker_state"

# Verify no errors
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=100 | grep "level=error" | wc -l
```

#### Post-Recovery Validation

```bash
# Verify all services healthy
kubectl get pods --all-namespaces | grep -E "(orchestrator-dynamic|worker-agents|service-registry|execution-ticket-service)"

# Verify metrics
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=up{job=~\"orchestrator-dynamic|worker-agents\"}" | jq

# Run full E2E test
./tests/phase2-flow-c-integration-test.sh

# Monitor for 30 minutes
watch -n 60 'curl -s "http://prometheus.monitoring:9090/api/v1/query?query=rate(neural_hive_flow_c_success_total[5m])" | jq ".data.result[0].value[1]"'
```

---

## Data Recovery Procedures

### MongoDB Collections

#### Backup Strategy

```bash
# Automated daily backups (configured in CronJob)
# 0 2 * * * /scripts/backup/backup-mongodb-orchestration.sh

# Manual backup
kubectl exec -n neural-hive-orchestration mongodb-0 -- \
  mongodump --uri mongodb://mongodb:27017/neural_hive --out /tmp/backup-$(date +%Y%m%d)

# Upload to S3
kubectl cp neural-hive-orchestration/mongodb-0:/tmp/backup-$(date +%Y%m%d) /tmp/mongodb-backup
tar -czf /tmp/mongodb-backup-$(date +%Y%m%d).tar.gz -C /tmp mongodb-backup
aws s3 cp /tmp/mongodb-backup-$(date +%Y%m%d).tar.gz s3://neural-hive-backups-prod/mongodb/orchestration/

# Create metadata
cat > /tmp/backup-metadata.json << EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "type": "mongodb",
  "database": "neural_hive",
  "collections": ["execution_tickets", "validation_audit", "workflow_results"],
  "size_bytes": $(du -b /tmp/mongodb-backup-$(date +%Y%m%d).tar.gz | cut -f1)
}
EOF
aws s3 cp /tmp/backup-metadata.json s3://neural-hive-backups-prod/mongodb/orchestration/backup-$(date +%Y%m%d).metadata.json
```

#### Restore Specific Collection

```bash
# Download and extract backup
aws s3 cp s3://neural-hive-backups-prod/mongodb/orchestration/backup-2024-01-15.tar.gz /tmp/
tar -xzf /tmp/backup-2024-01-15.tar.gz -C /tmp/

# Restore only execution_tickets
kubectl cp /tmp/mongodb-backup/neural_hive/execution_tickets.bson neural-hive-orchestration/mongodb-0:/tmp/

kubectl exec -n neural-hive-orchestration mongodb-0 -- \
  mongorestore --uri mongodb://mongodb:27017/neural_hive --nsInclude neural_hive.execution_tickets --drop /tmp/execution_tickets.bson

# Rebuild indexes for restored collection
kubectl exec -n neural-hive-orchestration mongodb-0 -- \
  mongosh mongodb://mongodb:27017/neural_hive --eval '
    db.execution_tickets.createIndex({ticket_id: 1}, {unique: true});
    db.execution_tickets.createIndex({plan_id: 1});
    db.execution_tickets.createIndex({status: 1});
  '
```

### Kafka Topics

#### Backup Strategy

```bash
# MirrorMaker continuous replication (configured in deployment)
# See: k8s/kafka/mirror-maker.yaml

# Manual backup (export messages for specific time range)
kubectl exec -n neural-hive-messaging kafka-0 -- \
  kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic execution.tickets \
  --from-beginning --max-messages 10000 > /tmp/execution-tickets-backup.json

# Upload to S3
aws s3 cp /tmp/execution-tickets-backup.json s3://neural-hive-backups-prod/kafka/topics/execution-tickets-$(date +%Y%m%d).json
```

#### Replay Messages

```bash
# Replay from backup
cat /tmp/execution-tickets-backup.json | \
kubectl exec -i -n neural-hive-messaging kafka-0 -- \
  kafka-console-producer.sh --bootstrap-server localhost:9092 --topic execution.tickets
```

### Temporal Workflows

#### Backup Strategy

```bash
# PostgreSQL automated backups (configured in CronJob)
# 0 1 * * * /scripts/backup/backup-postgres-temporal.sh

# Manual backup
kubectl exec -n temporal postgresql-temporal-0 -- \
  pg_dump -U temporal -d temporal -F c -f /tmp/temporal-backup-$(date +%Y%m%d).dump

# Upload to S3
kubectl cp temporal/postgresql-temporal-0:/tmp/temporal-backup-$(date +%Y%m%d).dump /tmp/
aws s3 cp /tmp/temporal-backup-$(date +%Y%m%d).dump s3://neural-hive-backups-prod/temporal/backups/
```

#### Point-in-Time Recovery

```bash
# Restore to specific timestamp
./scripts/maintenance/restore-postgres-temporal.sh --timestamp "2024-01-15 10:30:00"

# Or manually:
# 1. Restore base backup
# 2. Apply WAL files up to target time
# 3. Restart Temporal
```

---

## Escalation Procedures

### L1 - On-Call SRE

- Initial triage and incident classification
- Execute runbook procedures
- Rollback if possible
- Escalate if recovery > 30 minutes
- Contact: #sre-oncall, PagerDuty

### L2 - Service Owners

| Service | Team | Contact |
|---------|------|---------|
| Orchestrator Dynamic | @orchestration-team | #orchestration-team |
| Worker Agents | @execution-team | #execution-team |
| Service Registry | @registry-team | #registry-team |
| Databases | @data-team | #data-team |

### L3 - Engineering Manager

- Coordinate cross-team recovery
- Communicate with stakeholders
- Approve emergency procedures
- Contact: @eng-managers, #eng-leadership

### L4 - Database Reliability Engineering

- Complex database recovery
- Data integrity validation
- Performance optimization post-recovery
- Contact: @dbre-team, #database-reliability

---

## Communication Templates

### Incident Start

```
*INCIDENT: Flow C Complete Outage*

*SEVERITY:* P1 (Critical)
*START TIME:* 2024-01-15 10:00 UTC
*IMPACT:* Flow C unable to process decisions
*AFFECTED SERVICES:* Orchestrator Dynamic, Worker Agents, Service Registry
*STATUS:* Investigating
*INCIDENT COMMANDER:* @oncall-engineer
*ETA:* TBD

Please join #incident-flow-c-2024-01-15 for updates.
```

### Incident Update

```
*UPDATE: Flow C Recovery in Progress*

*TIME:* 2024-01-15 10:30 UTC
*PROGRESS:*
- [x] MongoDB restored from backup
- [x] Kafka topics recreated
- [ ] Services restarting
- [ ] E2E validation pending

*NEXT STEPS:* Validate E2E, monitor for 30 minutes
*ETA:* 11:00 UTC
```

### Incident Resolution

```
*RESOLVED: Flow C Fully Operational*

*TIME:* 2024-01-15 11:00 UTC
*DURATION:* 60 minutes
*ROOT CAUSE:* MongoDB cluster failure due to disk full
*RESOLUTION:* Restored from backup, increased disk size

*FOLLOW-UP:*
- Post-mortem scheduled for 2024-01-16 14:00 UTC
- Action items tracked in JIRA-12345

Thank you for your patience.
```

---

## Post-Mortem Template

### Incident Summary

- **Date:** 2024-01-15
- **Duration:** 60 minutes
- **Severity:** P1 (Critical)
- **Impact:** Flow C unable to process decisions for 60 minutes
- **Affected Users:** All users relying on automated execution

### Timeline

| Time (UTC) | Event |
|------------|-------|
| 10:00 | Incident detected (FlowCWorkersUnavailable alert) |
| 10:05 | On-call engineer acknowledged |
| 10:10 | Root cause identified (MongoDB disk full) |
| 10:15 | Recovery initiated |
| 10:30 | MongoDB restored from backup |
| 10:40 | Kafka topics verified |
| 10:45 | Services restarted |
| 10:55 | E2E validation passed |
| 11:00 | Incident resolved |

### Root Cause

MongoDB cluster ran out of disk space due to rapid growth of execution_tickets collection. The TTL index was not configured correctly, leading to unbounded growth.

### Contributing Factors

1. Missing disk usage alerts (threshold was set too high at 95%)
2. TTL index was configured but not applied to all collections
3. Backup retention policy kept too many local backups on disk

### Resolution

1. Restored MongoDB from last backup (1h old)
2. Increased disk size from 100GB to 500GB
3. Implemented TTL index on execution_tickets (30 days retention)
4. Cleared local backup files to free space

### Action Items

| Priority | Action | Owner | Due Date |
|----------|--------|-------|----------|
| P0 | Implement disk usage alerts (threshold: 80%) | @sre-team | 2024-01-16 |
| P1 | Verify TTL indexes on all collections | @data-team | 2024-01-17 |
| P1 | Review and update backup retention policy | @data-team | 2024-01-17 |
| P2 | Increase backup frequency to 30 minutes | @sre-team | 2024-01-20 |
| P2 | Add runbook for disk space recovery | @sre-team | 2024-01-20 |

### Lessons Learned

**What went well:**
- Alert fired promptly when workers became unavailable
- On-call engineer responded within 5 minutes
- Backup was recent and valid
- Recovery procedures in runbook were accurate

**What could be improved:**
- Earlier warning on disk space (80% instead of 95%)
- Automated TTL verification
- Faster root cause identification (took 5 minutes)

---

## References

- [Flow C Operations](./flow-c-operations.md)
- [Flow C Troubleshooting](./flow-c-troubleshooting.md)
- [Phase 2 Disaster Recovery](./phase2-disaster-recovery.md)
- [MongoDB Backup Scripts](../../scripts/backup/)
- [Kafka Backup Scripts](../../scripts/backup/)
- [Temporal Backup Scripts](../../scripts/backup/)
- [Emergency Deploy Script](../../scripts/deploy/deploy-phase2-emergency.sh)
