# Fluxo G - Production Deployment Checklist

## Pre-Deployment

### Code Quality

- [ ] All tests passing (unit + integration)
- [ ] No linting errors (`ruff check .`)
- [ ] Code formatted (`black .`)
- [ ] Security scan passed (`scripts/security_scan.py`)
- [ ] No known critical vulnerabilities
- [ ] Load tests passed (acceptable performance)

### Configuration

- [ ] Environment variables set for production
- [ ] Secrets stored in Vault/K8s secrets
- [ ] ConfigMaps reviewed and updated
- [ ] Resource limits defined (CPU, memory)
- [ ] Health check endpoints configured
- [ ] Graceful shutdown configured

### Dependencies

- [ ] Service Registry deployed and healthy
- [ ] Kafka cluster configured and tested
- [ ] MongoDB deployed and accessible
- [ ] Neo4j deployed and accessible
- [ ] Qdrant deployed and accessible
- [ ] Monitoring stack deployed (Prometheus, Grafana)

## Deployment Steps

### 1. Tag Release

```bash
# Tag the release
git tag -a v1.0.0-fluxo-g -m "Fluxo G Production Release v1.0.0"
git push origin v1.0.0-fluxo-g
```

### 2. Build Images

```bash
# Build for all services
for service in requirements-engineering documentation-generation knowledge-graph-rag approval-gateway; do
  docker build -t registry.neural-hive.local/$service:v1.0.0 services/$service/
  docker push registry.neural-hive.local/$service:v1.0.0
done
```

### 3. Update Kubernetes Manifests

```bash
# Update image tags
sed -i 's/image: .*/image: registry.neural-hive.local\/requirements-engineering:v1.0.0/g' k8s/production/requirements-engineering/deployment.yaml

# Verify changes
git diff k8s/production/
```

### 4. Deploy Services

```bash
# Deploy in order (dependencies first)
kubectl apply -f k8s/production/service-registry/
kubectl apply -f k8s/production/requirements-engineering/
kubectl apply -f k8s/production/documentation-generation/
kubectl apply -f k8s/production/knowledge-graph-rag/
kubectl apply -f k8s/production/approval-gateway/
kubectl apply -f k8s/production/orchestrator-dynamic/
```

### 5. Verify Deployment

```bash
# Check all pods are running
kubectl get pods -l app=fluxo-g -A

# Wait for rollouts to complete
kubectl rollout status deployment/requirements-engineering
kubectl rollout status deployment/documentation-generation
kubectl rollout status deployment/knowledge-graph-rag
kubectl rollout status deployment/approval-gateway
kubectl rollout status deployment/orchestrator-dynamic

# Check service registry connections
kubectl exec -it service-registry-xxxxx -- \
  grpcurl -plaintext localhost:8007 proto.service_registry.ServiceRegistry/DiscoverAgents \
  -d '{"capabilities": [], "filters": {}, "max_results": 50}'
```

## Post-Deployment

### Smoke Tests

```bash
# Test health endpoints
for port in 8010 8014 8016 8017; do
  curl -f http://production-service:$port/health || echo "FAIL: $port"
done

# Test service discovery
grpcurl -plaintext production-service:8007 \
  proto.service_registry.ServiceRegistry/DiscoverAgents \
  -d '{"capabilities": ["requirements_generation"], "filters": {}, "max_results": 5}'

# Test sample request
curl -X POST http://production-service:8010/api/v1/requirements/generate \
  -d '{"plan_text": "Test plan", "plan_id": "test-123"}'
```

### Monitoring Verification

- [ ] Prometheus scraping all targets
- [ ] Grafana dashboards displaying data
- [ ] No critical alerts firing
- [ ] Error rate within baseline (< 1%)
- [ ] P95 latency within baseline (< 1s)
- [ ] Service Registry showing 4+ connections

### Rollback Plan

If smoke tests fail:

```bash
# Immediate rollback
kubectl rollout undo deployment/requirements-engineering
kubectl rollout undo deployment/documentation-generation
kubectl rollout undo deployment/knowledge-graph-rag
kubectl rollout undo deployment/approval-gateway

# Verify rollback
kubectl rollout status deployment/requirements-engineering
```

## Monitoring First Hour

### Every 5 Minutes

- Check pod status (`kubectl get pods`)
- Check error rate in Grafana
- Check latency in Grafana
- Check for alerts in Alertmanager

### Every 15 Minutes

- Check Kafka consumer lag
- Check MongoDB connections
- Check memory usage
- Check CPU usage

### Hourly Summary

- Total requests processed
- Average response time
- Error rate
- Any incidents or anomalies

## Day 2 Operations

### Performance Tuning

- [ ] Review metrics and adjust resource limits if needed
- [ ] Tune database connections
- [ ] Adjust Kafka partition count if needed
- [ ] Update alert thresholds based on real data

### Documentation Updates

- [ ] Update operations manual with any lessons learned
- [ ] Update runbook if new issues discovered
- [ ] Document any configuration changes made during deployment

## Success Criteria

Deployment is successful if:

- [ ] All services pass smoke tests
- [ ] Error rate remains < 1% for first hour
- [ ] No critical alerts in first hour
- [ ] P95 latency remains < 1s under normal load
- [ ] All services remain registered in Service Registry
- [ ] No manual intervention required after first 30 minutes

## Contacts

- **On-call:** [@oncall]
- **Tech Lead:** [@tech-lead]
- **Engineering Manager:** [@em]
- **SRE Team:** #sre-oncall

## Emergency Contacts

- **Production Issues:** #production-alerts
- **Security Issues:** #security-response (page immediately)
- **Data Issues:** #data-team
