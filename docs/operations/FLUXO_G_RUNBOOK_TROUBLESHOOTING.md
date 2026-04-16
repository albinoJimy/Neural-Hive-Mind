# Fluxo G - Troubleshooting Runbook

## Incident Response

### Step 1: Identify the Issue

**Symptom Detection:**

| Symptom | Possible Cause | First Action |
|----------|----------------|--------------|
| Service unreachable | Service crash / Network issue | Check pod status |
| High error rate | Dependency down / Bug | Check dependency health |
| High latency | Resource constraint / DB slow | Check resource usage |
| Consumer lag increasing | Service too slow / Kafka issue | Check consumer metrics |

### Step 2: Check Service Status

```bash
# Check all Fluxo G pods
kubectl get pods -l app=fluxo-g -A

# Check pod details
kubectl describe pod requirements-engineering-xxxxx

# Check recent logs
kubectl logs --tail=100 deployment/requirements-engineering

# Check events
kubectl get events --sort-by='.lastTimestamp'
```

### Step 3: Verify Dependencies

```bash
# Check Service Registry
curl http://service-registry:8007/health

# Check Kafka
kafka-broker-api-versions --bootstrap-server kafka-0.kafka:9092

# Check MongoDB
kubectl exec -it mongo-0 -- mongo --eval "db.adminCommand('ping')"

# Check Service Registry connections
grpcurl -plaintext service-registry:8007 proto.service_registry.ServiceRegistry/DiscoverAgents \
  -d '{"capabilities": [], "filters": {}, "max_results": 50}'
```

### Step 4: Analyze Metrics

```bash
# Get error rate
sum by (job) (rate(http_requests_total{status=~"5..", job=~"requirements-engineering|documentation-generation|knowledge-graph-rag|approval-gateway"}[5m]))

# Get P95 latency
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="requirements-engineering"}[5m])) by (le))

# Get memory usage
process_resident_memory_bytes{job="requirements-engineering"} / 1024 / 1024

# Get CPU usage
rate(process_cpu_seconds_total{job="requirements-engineering"}[5m]) * 100
```

## Common Incidents

### Incident: Service Registration Failed

**Detection:**
```
grep "service_registration_failed" /var/log/fluxo-g/*.log
```

**Diagnosis:**
```bash
# 1. Check Service Registry is up
curl http://service-registry:8007/health

# 2. Check network connectivity
kubectl exec -it requirements-engineering-xxxxx -- nc -zv service-registry 8007

# 3. Check Service Registry logs
kubectl logs -f deployment/service-registry
```

**Resolution:**
1. Restart Service Registry if down
2. Fix network policies if needed
3. Restart affected service

### Incident: Kafka Consumer Lag

**Detection:**
```bash
kafka-consumer-groups --bootstrap-server kafka-0.kafka:9092 \
  --group requirements-engineering --describe
```

**Diagnosis:**
```bash
# 1. Check if service is processing
kubectl logs -f deployment/requirements-engineering | grep "Processing"

# 2. Check consumer group
kafka-consumer-groups --bootstrap-server kafka-0.kafka:9092 \
  --group requirements-engineering --members

# 3. Check topic messages
kafka-console-consumer --bootstrap-server kafka-0.kafka:9092 \
  --topic cognitive-plan --from-beginning --max-messages 10
```

**Resolution:**
1. Scale up service if overloaded
2. Reset consumer offsets if needed
3. Check for slow LLM calls (add timeouts)

### Incident: High Memory Usage

**Detection:**
```bash
kubectl top pod -l app=fluxo-g --containers
```

**Diagnosis:**
```bash
# 1. Check memory leaks
kubectl exec -it requirements-engineering-xxxxx -- \
  python -c "import tracemalloc; tracemalloc.start(); ...; print(tracemalloc.get_traced_memory())"

# 2. Check cache size
kubectl exec -it requirements-engineering-xxxxx -- \
  curl http://localhost:8010/metrics | grep cache
```

**Resolution:**
1. Clear caches if too large
2. Restart service (Kubernetes will recreate pod)
3. Increase memory limits

### Incident: LLM API Timeout

**Detection:**
```bash
grep "llm_api_timeout" /var/log/fluxo-g/*.log
```

**Diagnosis:**
```bash
# 1. Check LLM service connectivity
kubectl exec -it requirements-engineering-xxxxx -- \
  curl -X POST http://anthropic-service:8000/v1/messages -H "Content-Type: application/json" \
  -d '{"model": "claude-3-opus-20240229", "max_tokens": 10}'

# 2. Check timeout configuration
kubectl exec -it requirements-engineering-xxxxx -- \
  grep -r "timeout" /app/src/
```

**Resolution:**
1. Increase timeout if service is slow
2. Implement retry with exponential backoff
3. Add circuit breaker for LLM calls

## Recovery Procedures

### Full Service Restart

```bash
# 1. Scale down to zero
kubectl scale deployment/requirements-engineering --replicas=0

# 2. Wait for pods to terminate
kubectl wait --for=delete pod -l app=requirements-engineering --timeout=60s

# 3. Scale back up
kubectl scale deployment/requirements-engineering --replicas=1

# 4. Verify
kubectl rollout status deployment/requirements-engineering
```

### Database Recovery

```bash
# MongoDB - Emergency restore
kubectl exec -it mongo-0 -- mongorestore --archive=/backup/mongo-emergency.gz

# Verify data integrity
kubectl exec -it mongo-0 -- mongo neural_hive --eval "db.requirements.count()"
```

### Disaster Recovery

```bash
# 1. Switch to backup region
kubectl config use-context disaster-recovery-cluster

# 2. Restore from backup
kubectl apply -f k8s/disaster-recovery/

# 3. Verify services
for port in 8010 8014 8016 8017; do
  curl http://disaster-$port/health
done

# 4. Switch DNS
kubectl apply -f k8s/disaster-recovery/dns/
```

## Communication

### Incident Severity Levels

| Level | Description | Notification | Response Time |
|-------|-------------|----------------|---------------|
| P1 | Critical - service down completely | Page, Slack #incidents | 15 min |
| P2 | High - degraded performance | Slack #incidents | 1 hour |
| P3 | Medium - minor issues | Slack #fluxo-g | 1 business day |
| P4 | Low - cosmetic issues | Slack #fluxo-g | Next sprint |

### Incident Template

```
🚨 INCIDENT: [Service Name] - [Brief Description]

**Severity:** P1/P2/P3/P4
**Started:** [Timestamp]
**Owner:** [@username]

**Impact:**
- [ ] Service is down
- [ ] Users unable to [action]
- [ ] [Other impacts]

**Current Status:**
[What's happening now]

**Investigation:**
[What we're checking]

**Next Steps:**
1. [Action 1]
2. [Action 2]

**Updates:**
- [HH:MM] [Update 1]
- [HH:MM] [Update 2]
```

## Escalation Path

1. **On-call Engineer** (First responder)
   - Attempt resolution using this runbook
   - Create incident in Slack
   - Escalate if unresolved in 30 min (P1) / 2 hours (P2)

2. **Tech Lead** (Escalation point)
   - Provide architectural guidance
   - Coordinate cross-team dependencies
   - Make decisions on partial rollbacks

3. **Engineering Manager** (If needed)
   - Business impact assessment
   - Customer communication
   - Resource allocation

## Post-Incident

### Review Checklist

- [ ] Root cause identified
- [ ] Fix implemented and tested
- [ ] Incident timeline documented
- [ ] Runbook updated if needed
- [ ] Postmortem meeting scheduled
- [ ] Follow-up actions assigned

### Postmortem Template

```markdown
# Postmortem: [Incident Title]

## Summary
[Brief description of what happened]

## Timeline
| Time | Event |
|------|--------|
| HH:MM | [Event 1] |
| HH:MM | [Event 2] |

## Root Cause
[What caused the incident]

## Impact
[Users affected, duration, severity]

## Resolution
[How it was fixed]

## Lessons Learned
[What we can do better]

## Action Items
| [ ] Action | Owner | Due Date |
|-------------|--------|----------|
```
