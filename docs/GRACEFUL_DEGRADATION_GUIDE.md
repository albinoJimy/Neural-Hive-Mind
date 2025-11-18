# Graceful Degradation Guide - Neural Hive Mind

## 1. Overview

Graceful degradation is a design pattern where the system continues to operate with reduced functionality when dependencies are unavailable, rather than failing completely. This guide covers how Neural Hive Mind specialists handle graceful degradation.

### Key Principles

- **Fail Gracefully**: Specialists start and operate even if non-critical dependencies are unavailable
- **Retry with Backoff**: Connection attempts use exponential backoff to avoid overwhelming dependencies
- **Circuit Breaker Aware**: Respect existing circuit breakers to prevent cascading failures
- **Backward Compatible**: Changes don't break existing deployments
- **Observable**: Clear logging when operating in degraded mode

### Components Supporting Degradation

| Component | Full Mode | Degraded Mode | Impact |
|-----------|-----------|---------------|--------|
| **MLflow** | ML model inference enabled | Fallback to heuristics | Lower quality opinions, but functional |
| **Ledger (MongoDB)** | Opinions persisted to database | Opinions not persisted | No audit trail, but evaluations continue |
| **OpinionCache (Redis)** | Cache hits improve performance | No caching | Slower response times |
| **FeatureStore** | Feature persistence enabled | No persistence | Features not saved |

## 2. Degradation Scenarios

### Scenario A: MongoDB Unavailable

**Impact:** Ledger persistence disabled, opinions not saved to database

**Functionality:**
- Specialists continue evaluating plans using ML models and heuristics
- Opinions generated but not persisted
- Health checks show degraded status

**Detection:**
```bash
# Check logs
kubectl logs -n neural-hive-specialists <pod-name> | grep "Ledger unavailable"

# Check health endpoint
kubectl exec -n neural-hive-specialists <pod-name> -- curl -s http://localhost:8000/ready | jq
```

**Expected Log Messages:**
```
Ledger client unavailable - continuing without ledger persistence
Ledger unavailable - opinion not persisted
Operating in degraded mode: ledger_disabled
```

**Health Check Response:**
```json
{
  "status": "SERVING",
  "degraded": true,
  "degraded_reasons": ["ledger_unavailable"],
  "details": {
    "ledger": "unavailable",
    "mlflow": "healthy",
    "opinion_cache": "healthy"
  }
}
```

**Recovery:** Automatic when MongoDB becomes available (circuit breaker recovery after 60s)

---

### Scenario B: MLflow Unavailable

**Impact:** ML model inference disabled, fallback to rule-based evaluation

**Functionality:**
- Specialists use heuristic evaluation only
- Lower quality opinions but functional
- Performance may be faster (no model inference)

**Detection:**
```bash
kubectl logs -n neural-hive-specialists <pod-name> | grep "MLflow client unavailable"
```

**Expected Log Messages:**
```
MLflow client unavailable - continuing without ML models
Using heuristic evaluation (MLflow unavailable)
```

**Health Check Response:**
```json
{
  "status": "SERVING",
  "degraded": false,
  "details": {
    "mlflow_enabled": false,
    "ledger": "healthy"
  }
}
```

**Recovery:** Automatic when MLflow becomes available

---

### Scenario C: Redis Unavailable

**Impact:** Opinion cache disabled, no cache hits

**Functionality:**
- Every evaluation is fresh (no performance optimization from caching)
- Higher latency due to full evaluation each time
- All other features work normally

**Detection:**
```bash
kubectl logs -n neural-hive-specialists <pod-name> | grep "Opinion cache unavailable"
```

**Expected Log Messages:**
```
Opinion cache unavailable - continuing without cache
Cache miss (cache unavailable)
```

**Health Check Response:**
```json
{
  "status": "SERVING",
  "degraded": true,
  "degraded_reasons": ["cache_unavailable"],
  "details": {
    "opinion_cache": "unavailable",
    "ledger": "healthy"
  }
}
```

**Recovery:** Automatic when Redis becomes available

---

### Scenario D: Multiple Dependencies Unavailable

**Impact:** Combined effects of above scenarios

**Functionality:**
- Specialists operate with minimal functionality
- Heuristic-only evaluation
- No persistence or caching
- Fully functional for evaluation, but degraded quality and performance

**Detection:**
```bash
kubectl logs -n neural-hive-specialists <pod-name> | grep "degraded_mode=True"
```

**Health Check Response:**
```json
{
  "status": "SERVING",
  "degraded": true,
  "degraded_reasons": ["ledger_unavailable", "mlflow_unavailable", "cache_unavailable"],
  "details": {
    "ledger": "unavailable",
    "mlflow_enabled": false,
    "opinion_cache": "unavailable"
  }
}
```

## 3. Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_LEDGER` | `true` | Enable ledger feature |
| `LEDGER_REQUIRED` | `false` | Fail-fast if ledger unavailable (false = graceful) |
| `LEDGER_INIT_RETRY_ATTEMPTS` | `5` | Number of retry attempts |
| `LEDGER_INIT_RETRY_MAX_WAIT_SECONDS` | `30` | Max backoff time between retries |
| `STARTUP_SKIP_WARMUP_ON_DEPENDENCY_FAILURE` | `true` | Skip warmup if dependencies fail |
| `STARTUP_DEPENDENCY_CHECK_TIMEOUT_SECONDS` | `10` | Timeout for dependency checks |

### Helm Values Configuration

**Production (Fail-Gracefully):**
```yaml
config:
  enableLedger: true
  ledgerRequired: false  # Continue in degraded mode
  ledgerInitRetryAttempts: 5
  ledgerInitRetryMaxWaitSeconds: 30
```

**Production (Fail-Fast for Compliance):**
```yaml
config:
  enableLedger: true
  ledgerRequired: true  # Pod crashes if MongoDB unavailable
  ledgerInitRetryAttempts: 5
  ledgerInitRetryMaxWaitSeconds: 30
```

**Development:**
```yaml
config:
  enableLedger: true
  ledgerRequired: false  # Always graceful in dev
  ledgerInitRetryAttempts: 3  # Fewer retries for faster feedback
  ledgerInitRetryMaxWaitSeconds: 15
```

### Retry Logic Behavior

The ledger client uses exponential backoff for retries:

```
Attempt 1: Wait 2 seconds
Attempt 2: Wait 4 seconds
Attempt 3: Wait 8 seconds
Attempt 4: Wait 16 seconds
Attempt 5: Wait 30 seconds (capped at max)
```

Total maximum wait time: ~60 seconds before giving up

## 4. Monitoring & Observability

### Metrics to Watch

```promql
# Degraded mode indicator (1 = degraded, 0 = normal)
specialist_degraded_mode{component="ledger"}

# Failed save operations
specialist_ledger_save_failures_total

# Circuit breaker state
specialist_circuit_breaker_state{client="ledger"}

# Retry attempts
specialist_ledger_init_retries_total
```

### Alerting Rules

**Example Prometheus Alert:**
```yaml
- alert: SpecialistDegradedMode
  expr: specialist_degraded_mode{component="ledger"} == 1
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Specialist {{ $labels.specialist_type }} in degraded mode"
    description: "Ledger unavailable for 5+ minutes"

- alert: SpecialistLedgerSaveFailures
  expr: rate(specialist_ledger_save_failures_total[5m]) > 0.1
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "High ledger save failure rate"
    description: "{{ $value }} failures/sec for {{ $labels.specialist_type }}"
```

### Log Patterns

**Successful Initialization:**
```
Ledger client initialized successfully
MongoDB connection established
Ledger indexes created successfully
```

**Graceful Degradation:**
```
Ledger client unavailable - continuing without ledger persistence
Ledger unavailable - opinion not persisted
Operating in degraded mode: ledger_disabled
```

**Retry Attempts:**
```
Failed to initialize ledger client (retry_attempt=true)
Retrying connection to MongoDB (attempt 2/5)
```

**Circuit Breaker Events:**
```
Circuit breaker opened for ledger_client
Circuit breaker half-open, attempting recovery
Circuit breaker closed, ledger_client recovered
```

## 5. Operational Procedures

### Procedure: Deploy with Degraded Mode

**Use Case:** Deploy specialists before dependencies are ready

```bash
# 1. Set graceful degradation in values
cat > /tmp/graceful-config.yaml <<EOF
config:
  ledgerRequired: false
EOF

# 2. Deploy specialists
helm upgrade specialist-business ./helm-charts/specialist-business \
  -f environments/dev/helm-values/specialist-business-values.yaml \
  -f /tmp/graceful-config.yaml \
  -n neural-hive-specialists

# 3. Verify pods start successfully
kubectl get pods -n neural-hive-specialists -w

# 4. Check degraded status
kubectl exec -n neural-hive-specialists <pod-name> -- \
  curl -s http://localhost:8000/ready | jq '.degraded'

# 5. Deploy MongoDB
helm install mongodb ...

# 6. Wait for automatic recovery
sleep 70  # Circuit breaker recovery timeout

# 7. Verify recovery
kubectl exec -n neural-hive-specialists <pod-name> -- \
  curl -s http://localhost:8000/ready | jq '.details.ledger'
```

**Expected Outcome:** Specialists start immediately, operate in degraded mode, automatically recover when MongoDB is available

---

### Procedure: Force Fail-Fast Mode

**Use Case:** Production environment where ledger is critical for compliance

```bash
# 1. Set fail-fast mode
cat > /tmp/fail-fast-config.yaml <<EOF
config:
  ledgerRequired: true
EOF

# 2. Deploy specialists
helm upgrade specialist-business ./helm-charts/specialist-business \
  -f /tmp/fail-fast-config.yaml \
  -n neural-hive-specialists

# 3. If MongoDB is down, pods will crash
kubectl get pods -n neural-hive-specialists
# Expected: CrashLoopBackOff

# 4. Check logs
kubectl logs -n neural-hive-specialists <pod-name> --tail=20
# Expected: "Ledger required but unavailable - exiting"

# 5. Fix MongoDB issue
kubectl get pods -n mongodb-cluster

# 6. Pods automatically restart and succeed
kubectl get pods -n neural-hive-specialists -w
```

**Expected Outcome:** Pods crash if MongoDB unavailable, automatically start when MongoDB is fixed

---

### Procedure: Test Degradation Locally

**Use Case:** Verify graceful degradation works correctly

```bash
# 1. Start with all dependencies healthy
kubectl get pods -A

# 2. Simulate MongoDB failure
kubectl scale statefulset mongodb -n mongodb-cluster --replicas=0

# 3. Restart specialist pod
kubectl delete pod -l app.kubernetes.io/name=specialist-business \
  -n neural-hive-specialists

# 4. Verify pod starts successfully
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=specialist-business \
  -n neural-hive-specialists --timeout=300s

# 5. Check degraded status
kubectl exec -n neural-hive-specialists <pod-name> -- \
  curl -s http://localhost:8000/ready

# 6. Test evaluation still works
kubectl exec -n neural-hive-specialists <pod-name> -- \
  grpcurl -plaintext -d '{"plan_id": "test-123", ...}' \
  localhost:50051 specialist.SpecialistService/EvaluatePlan

# 7. Restore MongoDB
kubectl scale statefulset mongodb -n mongodb-cluster --replicas=1

# 8. Wait for recovery
sleep 70

# 9. Verify full functionality restored
kubectl exec -n neural-hive-specialists <pod-name> -- \
  curl -s http://localhost:8000/ready | jq '.degraded'
# Expected: false
```

## 6. Troubleshooting

### Issue: Pods crash despite graceful degradation

**Symptoms:** CrashLoopBackOff even with `ledgerRequired: false`

**Diagnosis:**
```bash
# Check if error is from different component
kubectl logs <pod> --previous | grep -i "error\|exception\|fatal"

# Verify env vars are injected
kubectl exec <pod> -- env | grep LEDGER

# Check if error is in different component
kubectl logs <pod> --previous | grep -v "ledger" | grep -i "error"
```

**Solutions:**
1. Check Neo4j availability (also a critical dependency)
2. Verify all env vars are correctly injected
3. Check startup probe timeout (may be too short)
4. Review logs for non-MongoDB errors

---

### Issue: Degraded mode not recovering

**Symptoms:** Ledger stays unavailable even after MongoDB is healthy

**Diagnosis:**
```bash
# Test MongoDB connectivity from pod
kubectl exec <pod> -- python -c \
  "from pymongo import MongoClient; \
   MongoClient('mongodb://...').admin.command('ping')"

# Check circuit breaker state
kubectl logs <pod> | grep "circuit_breaker"

# Check if circuit breaker recovery timeout has passed
kubectl logs <pod> | grep "Circuit breaker" | tail -5
```

**Solutions:**
1. Wait for circuit breaker recovery timeout (default 60s)
2. Check if circuit breaker is stuck in open state
3. Restart pod to force reconnection:
   ```bash
   kubectl delete pod <pod-name>
   ```
4. Verify MongoDB is truly healthy and accepting connections

---

### Issue: High frequency of degradation events

**Symptoms:** Specialists frequently entering/exiting degraded mode

**Diagnosis:**
```bash
# Check degradation frequency
kubectl logs <pod> | grep "degraded_mode" | wc -l

# Check MongoDB stability
kubectl logs -n mongodb-cluster <mongodb-pod> | grep -i "connection"

# Check network connectivity
kubectl exec <pod> -- ping mongodb.mongodb-cluster.svc.cluster.local
```

**Solutions:**
1. Investigate MongoDB instability (OOMKills, restarts)
2. Check network policies or service mesh issues
3. Increase retry attempts and backoff times:
   ```yaml
   config:
     ledgerInitRetryAttempts: 10
     ledgerInitRetryMaxWaitSeconds: 60
   ```
4. Review circuit breaker settings (may be too sensitive)

## 7. Best Practices

### Development Environments

```yaml
# Dev environment configuration
config:
  # Use graceful mode for faster iteration
  ledgerRequired: false

  # Reduce retries for quicker feedback
  ledgerInitRetryAttempts: 3
  ledgerInitRetryMaxWaitSeconds: 15

  # Enable verbose logging
  logLevel: DEBUG

  # Skip warmup on failure for faster startup
  startupSkipWarmupOnDependencyFailure: true
```

**Benefits:**
- Faster iteration when dependencies are down
- Easier debugging with verbose logs
- Quick feedback loop

---

### Production Environments

**Option 1: Graceful Degradation (Availability > Consistency)**
```yaml
config:
  # Allow degraded operation
  ledgerRequired: false

  # More retries for transient failures
  ledgerInitRetryAttempts: 5
  ledgerInitRetryMaxWaitSeconds: 30

  # Monitor degraded mode
  # Set up alerts for prolonged degradation
```

**When to Use:** High availability is critical, can tolerate temporary loss of audit trail

**Option 2: Fail-Fast (Consistency > Availability)**
```yaml
config:
  # Require ledger for compliance
  ledgerRequired: true

  # Still retry for transient failures
  ledgerInitRetryAttempts: 5
  ledgerInitRetryMaxWaitSeconds: 30
```

**When to Use:** Ledger is critical for compliance/regulatory requirements, cannot operate without audit trail

---

### Staging Environments

**Use staging to test both modes:**

```bash
# Test graceful degradation
helm upgrade specialist-business ./helm-charts/specialist-business \
  --set config.ledgerRequired=false \
  -n staging

# Simulate failure and verify recovery
kubectl scale statefulset mongodb -n mongodb-cluster --replicas=0
# ... test degraded operation ...
kubectl scale statefulset mongodb -n mongodb-cluster --replicas=1
# ... verify recovery ...

# Test fail-fast mode
helm upgrade specialist-business ./helm-charts/specialist-business \
  --set config.ledgerRequired=true \
  -n staging

# Simulate failure and verify pod crashes
kubectl scale statefulset mongodb -n mongodb-cluster --replicas=0
kubectl get pods -n staging  # Should see CrashLoopBackOff
```

---

### Monitoring Strategy

1. **Always monitor degraded mode:**
   ```promql
   specialist_degraded_mode{component="ledger"} == 1
   ```

2. **Alert on prolonged degradation:**
   - Warning: Degraded for >5 minutes
   - Critical: Degraded for >30 minutes

3. **Track save failures:**
   ```promql
   rate(specialist_ledger_save_failures_total[5m]) > 0
   ```

4. **Monitor circuit breaker state:**
   ```promql
   specialist_circuit_breaker_state{client="ledger"} != 0
   ```

5. **Dashboard widgets:**
   - Current degraded status (gauge)
   - Degradation events over time (graph)
   - Save failure rate (graph)
   - Circuit breaker state history (heatmap)

---

### Automated Recovery

**Implement automated remediation for common issues:**

```yaml
# Kubernetes operator or external controller
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: specialist-auto-remediation
spec:
  groups:
  - name: specialist-remediation
    rules:
    - alert: SpecialistDegradedTooLong
      expr: specialist_degraded_mode{component="ledger"} == 1
      for: 10m
      annotations:
        action: "restart_mongodb"
        summary: "Trigger MongoDB restart if degraded >10m"
```

**Recovery actions:**
1. Restart MongoDB pod
2. Scale MongoDB StatefulSet
3. Restart specialist pods
4. Clear circuit breaker state

## 8. Implementation Details

### Code References

| Component | File | Line |
|-----------|------|------|
| Graceful degradation logic | `libraries/python/neural_hive_specialists/base_specialist.py` | 99-108 |
| Ledger validation | `libraries/python/neural_hive_specialists/base_specialist.py` | 1058-1061 |
| Health check with degradation | `libraries/python/neural_hive_specialists/base_specialist.py` | 1512-1523 |
| Retry logic | `libraries/python/neural_hive_specialists/ledger_client.py` | 174-202 |
| Configuration fields | `libraries/python/neural_hive_specialists/config.py` | 135-154 |

### Related Documentation

- [RESOURCE_TUNING_GUIDE.md](./RESOURCE_TUNING_GUIDE.md) - Resource optimization
- [DIAGNOSTIC_PODS_CRASHLOOP.md](../DIAGNOSTIC_PODS_CRASHLOOP.md) - Pod troubleshooting
- [REMEDIATION_GUIDE_PODS.md](../REMEDIATION_GUIDE_PODS.md) - Remediation procedures

### Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│           Specialist Pod Startup                │
└─────────────────────────────────────────────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │  Initialize Components │
         └────────────────────────┘
                      │
    ┌─────────────────┼─────────────────┐
    ▼                 ▼                 ▼
┌────────┐      ┌──────────┐      ┌──────────┐
│ MLflow │      │  Ledger  │      │  Cache   │
│ (try)  │      │  (try)   │      │  (try)   │
└────────┘      └──────────┘      └──────────┘
    │                 │                 │
    ├─Success─────────┼─────────────────┤
    │                 │                 │
    ├─Failure────┐    ├─Failure────┐    ├─Failure────┐
    │            │    │            │    │            │
    ▼            ▼    ▼            ▼    ▼            ▼
┌────────┐  ┌────────┐┌──────────┐┌────────┐┌──────────┐
│ Enabled│  │ Disabled││ Retry 5x ││ Disabled││ Disabled │
└────────┘  └────────┘└──────────┘└────────┘└──────────┘
                           │
                ┌──────────┴──────────┐
                ▼                     ▼
         ┌────────────┐        ┌────────────┐
         │  Success   │        │   Failure  │
         │ (Enabled)  │        │            │
         └────────────┘        └────────────┘
                                      │
                            ┌─────────┴─────────┐
                            ▼                   ▼
                   ┌──────────────────┐  ┌──────────────────┐
                   │ ledgerRequired   │  │ ledgerRequired   │
                   │    = false       │  │    = true        │
                   │                  │  │                  │
                   │ Set to None      │  │ Exit(1)          │
                   │ Continue startup │  │ CrashLoopBackOff │
                   └──────────────────┘  └──────────────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │   Pod Running    │
                   │ (Degraded Mode)  │
                   └──────────────────┘
```

## 9. Future Improvements

### Planned Enhancements

1. **Smart Degradation Levels:**
   - Level 0: Full functionality
   - Level 1: Cache unavailable
   - Level 2: Ledger unavailable
   - Level 3: MLflow unavailable
   - Level 4: Multiple dependencies unavailable

2. **Degradation Metrics Dashboard:**
   - Real-time degradation status
   - Historical degradation events
   - Impact analysis on opinion quality

3. **Auto-Recovery Policies:**
   - Configurable recovery strategies
   - Dependency health checks before recovery
   - Gradual traffic shifting after recovery

4. **Degradation Testing Framework:**
   - Chaos engineering for dependencies
   - Automated degradation scenarios
   - Performance benchmarks in degraded mode

### Contributing

To improve graceful degradation:

1. Test new dependency integrations with degradation
2. Add metrics for new degradation scenarios
3. Document new degradation modes
4. Update health checks to reflect new states

---

**Last Updated:** 2025-01-10
**Version:** 1.0
**Authors:** Neural Hive Mind Team
