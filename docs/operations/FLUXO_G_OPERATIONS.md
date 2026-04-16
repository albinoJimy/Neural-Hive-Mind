# Fluxo G - Operations Manual

## Overview

This document provides operational procedures for managing Fluxo G engineering services in production.

## Services

| Service | Port | Health Check | Dependencies |
|---------|------|--------------|--------------|
| requirements-engineering | 8010 | GET /health | Kafka, MongoDB, Service Registry |
| documentation-generation | 8014 | GET /health | Kafka, MongoDB, Service Registry |
| knowledge-graph-rag | 8016 | GET /health | Neo4j, Qdrant, Service Registry |
| approval-gateway | 8017 | GET /health | Kafka, MongoDB, JWT Service, Service Registry |

## Prerequisites

- Docker & Docker Compose
- kubectl (for Kubernetes)
- Access to service logs (ELK/Loki)
- Monitoring dashboards (Grafana)

## Startup Sequence

### 1. Start Infrastructure

```bash
# Start dependencies
docker-compose -f docker-compose.infra.yml up -d

# Verify Kafka is ready
docker-compose exec kafka kafka-topics --list --bootstrap-server localhost:9092

# Verify MongoDB is ready
docker-compose exec mongo mongo --eval "db.adminCommand('ping')"
```

### 2. Start Service Registry

```bash
# Service Registry must start first
cd services/service-registry
python -m src.main

# Verify
curl http://localhost:8007/health
```

### 3. Start Engineering Services

```bash
# Start in parallel
cd services/requirements-engineering && python -m src.main &
cd services/documentation-generation && python -m src.main &
cd services/knowledge-graph-rag && python -m src.main &
cd services/approval-gateway && python -m src.main &

# Verify all are up
for port in 8010 8014 8016 8017; do
    curl http://localhost:$port/health
done
```

### 4. Start Orchestrator

```bash
cd services/orchestrator-dynamic
python -m src.main
```

## Health Checks

### Individual Services

```bash
# Requirements Engineering
curl http://localhost:8010/health

# Documentation Generation
curl http://localhost:8014/health

# Knowledge Graph RAG
curl http://localhost:8016/health

# Approval Gateway
curl http://localhost:8017/health

# Service Registry
curl http://localhost:8007/health
```

### Service Registry Discovery

```bash
# List all registered services
grpcurl -plaintext localhost:8007 proto.service_registry.ServiceRegistry/DiscoverAgents \
  -d '{"capabilities": [], "filters": {}, "max_results": 50}'

# Check specific service type
grpcurl -plaintext localhost:8007 proto.service_registry.ServiceRegistry/DiscoverAgents \
  -d '{"capabilities": ["requirements_generation"], "filters": {}, "max_results": 5}'
```

## Graceful Shutdown

### Single Service

```bash
# Send SIGTERM for graceful shutdown
kill -TERM $(pgrep -f "requirements-engineering")

# Service will:
# 1. Stop accepting new requests
# 2. Complete in-flight requests
# 3. Deregister from Service Registry
# 4. Close Kafka connections
# 5. Shutdown
```

### All Services

```bash
# Using docker-compose
docker-compose down

# Using Kubernetes
kubectl delete deployment -l app=fluxo-g
kubectl wait --for=delete pod -l app=fluxo-g --timeout=60s
```

## Log Analysis

### Service Logs

```bash
# View logs for a service
docker-compose logs -f requirements-engineering

# Kubernetes logs
kubectl logs -f deployment/requirements-engineering

# All Fluxo G services
kubectl logs -l app=fluxo-g --all-containers=true -f
```

### Common Log Patterns

```bash
# Service registration failures
grep "service_registration_failed" /var/log/fluxo-g/*.log

# Kafka consumer lag
grep "consumer_lag" /var/log/fluxo-g/*.log

# LLM token usage
grep "llm_tokens_used" /var/log/fluxo-g/*.log

# High latency requests
grep "duration_ms.*>[0-9]\{4,\}" /var/log/fluxo-g/*.log
```

## Troubleshooting

### Service Won't Start

1. Check Service Registry is running:
   ```bash
   curl http://localhost:8007/health
   ```

2. Check port availability:
   ```bash
   netstat -tulpn | grep -E '8010|8014|8016|8017'
   ```

3. Check logs for errors:
   ```bash
   docker-compose logs service-name
   ```

4. Verify environment variables:
   ```bash
   docker-compose exec service-name env | grep KAFKA
   ```

### High Error Rate

1. Check service dependencies:
   ```bash
   # Kafka connectivity
   docker-compose exec requirements-engineering python -c "
   from src.consumers.cognitive_plan_consumer import CognitivePlanConsumer
   import asyncio
   consumer = CognitivePlanConsumer()
   asyncio.run(consumer.start())
   "
   ```

2. Check MongoDB connection:
   ```bash
   docker-compose exec mongo mongo --eval "db.stats()"
   ```

3. Check resource usage:
   ```bash
   docker stats $(docker ps -q --filter "name=fluxo-g")
   ```

### Kafka Consumer Lag

1. Check consumer lag:
   ```bash
   kafka-consumer-groups --bootstrap-server localhost:9092 \
     --group requirements-engineering --describe
   ```

2. Reset consumer group (if needed):
   ```bash
   kafka-consumer-groups --bootstrap-server localhost:9092 \
     --group requirements-engineering --reset-offsets --to-earliest \
     --topic cognitive-plan --execute
   ```

3. Scale consumers (Kubernetes):
   ```bash
   kubectl scale deployment/requirements-engineering --replicas=3
   ```

## Scaling

### Horizontal Scaling

```bash
# Scale up documentation-generation (stateless)
kubectl scale deployment/documentation-generation --replicas=3

# Scale up requirements-engineering (ensure consumer group partitioning)
kubectl scale deployment/requirements-engineering --replicas=3
```

### Vertical Scaling

```yaml
# Update deployment resources
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "2000m"
```

## Backup & Recovery

### MongoDB Backup

```bash
# Create backup
docker-compose exec mongo mongodump --archive=/backup/mongo-backup-$(date +%Y%m%d).gz

# Restore from backup
docker-compose exec mongo mongorestore --archive=/backup/mongo-backup-20260416.gz
```

### Kafka Backup

```bash
# Mirror topics
kafka-mirror-maker --producer.config backup.config \
  --consumer.config source.config --whitelist topic.*
```

## Deployment

### Deploy to Staging

```bash
# Build and push images
for service in requirements-engineering documentation-generation knowledge-graph-rag approval-gateway; do
  docker build -t registry.neural-hive.local/$service:staging services/$service/
  docker push registry.neural-hive.local/$service:staging
done

# Deploy to Kubernetes
kubectl apply -f k8s/staging/
kubectl rollout status deployment/requirements-engineering
```

### Deploy to Production

```bash
# Use production tag
for service in requirements-engineering documentation-generation knowledge-graph-rag approval-gateway; do
  docker build -t registry.neural-hive.local/$service:prod services/$service/
  docker push registry.neural-hive.local/$service:prod
done

# Deploy with canary strategy
kubectl apply -f k8s/production/
kubectl rollout status deployment/requirements-engineering
```

### Rollback

```bash
# Rollback to previous version
kubectl rollout undo deployment/requirements-engineering

# Rollback to specific revision
kubectl rollout undo deployment/requirements-engineering --to-revision=3
```

## Monitoring

### Key Metrics to Watch

1. **Service Health**
   - All services reporting `up: 1`
   - All services connected to Service Registry

2. **Request Rate**
   - Baseline: 10-100 req/s per service
   - Alert if: < 1 req/s for 5 min (service may be down)

3. **Error Rate**
   - Baseline: < 1%
   - Alert if: > 5% for 5 min

4. **Latency**
   - P50: < 100ms
   - P95: < 1s
   - P99: < 5s
   - Alert if: P95 > 5s for 5 min

5. **Kafka Consumer Lag**
   - Baseline: < 100 messages
   - Alert if: > 1000 messages for 10 min

## Contacts

- On-call: #fluxo-g-oncall
- Development: #fluxo-g-dev
- Architecture: #architecture

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-04-16 | Initial version | Claude Code |
