# Resource Tuning Guide - Neural Hive Mind

## 1. Overview

This guide covers resource optimization and tuning for Neural Hive Mind specialists in Kubernetes. Proper resource configuration ensures pods start successfully, perform well, and don't overwhelm the cluster.

### Why Resource Tuning Matters

- **Cluster Capacity**: Limited resources can cause Pending pods
- **Startup Time**: Incorrect probe settings cause CrashLoopBackOff
- **Performance**: Under-resourced pods are throttled or OOMKilled
- **Cost**: Over-provisioned resources waste money in cloud environments

### Trade-offs

| Aspect | High Resources | Low Resources |
|--------|----------------|---------------|
| **Startup Time** | Faster model loading | Slower startup |
| **Performance** | Better throughput | CPU throttling, memory pressure |
| **Scheduling** | May not fit on nodes | Easier to schedule |
| **Cost** | Higher cloud costs | Lower costs |

## 2. Resource Requests & Limits

### Understanding Requests vs Limits

- **Requests**: Guaranteed resources Kubernetes reserves for the pod
- **Limits**: Maximum resources the pod can use (burst capacity)

```yaml
resources:
  requests:
    cpu: 500m      # Guaranteed 0.5 CPU cores
    memory: 1Gi    # Guaranteed 1 GiB RAM
  limits:
    cpu: 2         # Can burst up to 2 CPU cores
    memory: 4Gi    # Hard limit at 4 GiB (OOMKill if exceeded)
```

### Default Values (Production)

**Current defaults in `values.yaml`:**
```yaml
resources:
  requests:
    cpu: 500m      # 0.5 CPU cores
    memory: 1Gi    # 1 GiB RAM
  limits:
    cpu: 2         # 2 CPU cores
    memory: 4Gi    # 4 GiB RAM
```

**Why these values:**
- 500m CPU: Sufficient for ML model inference with scikit-learn/XGBoost
- 1Gi memory: Enough to load models (~200-500MB) + application overhead
- 2 CPU limit: Allows burst during concurrent evaluations
- 4Gi memory: Headroom for large models and multiple concurrent requests

---

### Recommended Values by Environment

#### Development (Local Clusters, Limited Resources)

**Use Case:** Minikube, kind, Docker Desktop with limited RAM/CPU

```yaml
resources:
  requests:
    cpu: 250m      # Reduced for resource-constrained clusters
    memory: 512Mi  # Minimum for ML model loading
  limits:
    cpu: 1
    memory: 2Gi
```

**Trade-offs:**
- ✅ Can run on laptop/workstation
- ✅ Faster scheduling
- ⚠️ Slower model loading (30-60s)
- ⚠️ Lower concurrent request capacity

**Deploy Command:**
```bash
helm upgrade specialist-business ./helm-charts/specialist-business \
  -f environments/dev/helm-values/specialist-business-values.yaml \
  -n neural-hive-specialists
```

---

#### Staging (Similar to Production)

**Use Case:** Pre-production testing with production-like workload

```yaml
resources:
  requests:
    cpu: 500m
    memory: 1Gi
  limits:
    cpu: 2
    memory: 4Gi
```

**Why same as production:**
- Catch resource-related issues before production
- Validate performance characteristics
- Test auto-scaling behavior

---

#### Production (High Availability)

**Use Case:** Production workloads with SLA requirements

```yaml
resources:
  requests:
    cpu: 500m      # Guaranteed resources
    memory: 1Gi
  limits:
    cpu: 2         # Burst capacity
    memory: 4Gi
```

**With Horizontal Pod Autoscaling:**
```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80
```

---

#### Production (Large Models >500MB)

**Use Case:** Specialists with large ML models or embeddings

```yaml
resources:
  requests:
    cpu: 1         # More CPU for faster model loading
    memory: 2Gi    # More memory for large models
  limits:
    cpu: 4
    memory: 8Gi
```

**Indicators you need this:**
- Model files >500MB
- Startup time >5 minutes consistently
- OOMKilled events in logs
- "Cannot allocate memory" errors

---

### Tuning Guidelines

#### When to INCREASE Requests

**Symptom: OOMKilled (Out of Memory)**
```bash
# Check for OOMKills
kubectl describe pod <pod-name> -n neural-hive-specialists | grep OOMKilled

# Check last termination reason
kubectl get pod <pod-name> -n neural-hive-specialists \
  -o jsonpath='{.status.containerStatuses[0].lastState.terminated.reason}'
```

**Solution:**
```yaml
resources:
  requests:
    memory: 2Gi    # Double current value
  limits:
    memory: 6Gi    # Keep 3x ratio
```

---

**Symptom: High CPU Throttling**
```bash
# Check CPU usage vs limits
kubectl top pod <pod-name> -n neural-hive-specialists

# Expected output showing throttling:
# NAME                                  CPU(cores)   MEMORY(bytes)
# specialist-business-7d9f8b6c4d-x8k2p  1950m        1200Mi
#                                       ^^ near limit, being throttled
```

**Solution:**
```yaml
resources:
  requests:
    cpu: 1         # Increase from 500m
  limits:
    cpu: 3         # Increase proportionally
```

---

**Symptom: Slow Startup (>5 minutes)**

Check logs for slow model loading:
```bash
kubectl logs <pod-name> | grep "model_loading" | tail -5
```

**Solution:**
```yaml
resources:
  requests:
    cpu: 1         # More CPU for faster I/O
    memory: 2Gi    # More memory for buffering
```

---

#### When to DECREASE Requests

**Symptom: Pods Stuck in Pending**
```bash
# Check pending reason
kubectl describe pod <pod-name> -n neural-hive-specialists | grep -A 5 "Events"

# Expected output:
# Warning  FailedScheduling  Insufficient cpu (need 500m, available 300m)
```

**Solution:**
```yaml
resources:
  requests:
    cpu: 250m      # Reduce to fit on available nodes
    memory: 512Mi
```

---

**Symptom: Low Resource Utilization (<30%)**
```bash
# Check actual usage over time
kubectl top pod -n neural-hive-specialists --containers

# Expected output showing under-utilization:
# POD                                   CONTAINER  CPU(cores)  MEMORY(bytes)
# specialist-business-7d9f8b6c4d-x8k2p  specialist 150m        400Mi
#                                                  ^^ Only 30% of 500m request
```

**Solution:**
```yaml
resources:
  requests:
    cpu: 200m      # Reduce to match actual usage + buffer
    memory: 512Mi  # Reduce to match actual usage + buffer
```

---

### Monitoring Commands

```bash
# Current resource usage (live)
kubectl top pods -n neural-hive-specialists

# Detailed resource requests vs limits
kubectl describe pod <pod-name> -n neural-hive-specialists | grep -A 10 "Limits\|Requests"

# Check for OOMKills
kubectl get pods -n neural-hive-specialists \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.containerStatuses[0].lastState.terminated.reason}{"\n"}{end}' \
  | grep OOM

# Historical resource usage (requires metrics-server)
kubectl top pods -n neural-hive-specialists --containers --use-protocol-buffers

# CPU throttling metrics (requires cAdvisor)
kubectl exec -n kube-system <metrics-server-pod> -- \
  curl -s http://localhost:10255/stats/summary | jq '.pods[] | select(.podRef.name | contains("specialist"))'
```

---

## 3. Startup Probe Configuration

### Purpose

Startup probes allow extra time for initial container startup (loading ML models, connecting to dependencies) before liveness probes take over.

### Default Values (Production)

```yaml
startupProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10   # Wait 10s before first check
  periodSeconds: 10         # Check every 10s
  timeoutSeconds: 5         # Each check has 5s timeout
  failureThreshold: 30      # 30 failures = 5 minutes max
  successThreshold: 1       # 1 success = startup complete
```

**Calculation:** `initialDelaySeconds + (periodSeconds × failureThreshold) = 10s + (10s × 30) = 310s = ~5 minutes`

### Tuning by Scenario

#### Scenario A: Fast Clusters (SSD, High CPU)

**Environment:** Production with NVMe SSDs, 8+ CPU cores per node

```yaml
startupProbe:
  initialDelaySeconds: 5    # Reduced
  periodSeconds: 10
  failureThreshold: 20      # 20 * 10s = 3.3 minutes
```

**Why:** Fast I/O and CPU allow quicker model loading

---

#### Scenario B: Slow Clusters (HDD, Limited CPU)

**Environment:** Development with HDDs, 2-4 CPU cores per node

```yaml
startupProbe:
  initialDelaySeconds: 15   # Increased
  periodSeconds: 15         # Increased
  failureThreshold: 40      # 40 * 15s = 10 minutes
```

**Why:** Slower I/O and CPU contention require more patience

---

#### Scenario C: Large ML Models (>500MB)

**Environment:** Specialists with large embeddings or ensemble models

```yaml
startupProbe:
  initialDelaySeconds: 20
  periodSeconds: 15
  failureThreshold: 60      # 60 * 15s = 15 minutes
```

**Why:** Large model files take longer to load from disk and decompress

---

#### Scenario D: Development (Frequent Restarts)

**Environment:** Local development with code changes

```yaml
startupProbe:
  initialDelaySeconds: 15
  periodSeconds: 15
  failureThreshold: 40      # Generous timeout for debugging
```

**Why:** Developers may attach debuggers or need extra time to investigate

---

### Diagnostic Commands

```bash
# Check startup probe failures
kubectl describe pod <pod-name> -n neural-hive-specialists | grep -A 5 "Startup probe failed"

# Check actual startup time from logs
START=$(kubectl logs <pod-name> | grep "Starting specialist" | head -1 | awk '{print $1}')
READY=$(kubectl logs <pod-name> | grep "Specialist ready" | head -1 | awk '{print $1}')

# Calculate startup duration
echo "Startup time: $(( $(date -d "$READY" +%s) - $(date -d "$START" +%s) )) seconds"

# Watch startup progress in real-time
kubectl logs -f <pod-name> | grep -E "Starting|initialized|ready|Loading model"
```

### Common Issues

**Issue: "Startup probe failed: HTTP probe failed"**

```bash
# Check if application is actually starting
kubectl logs <pod-name> | tail -50

# Check if health endpoint is responding
kubectl exec <pod-name> -- curl -v http://localhost:8000/health

# Increase failureThreshold
helm upgrade specialist-business ./helm-charts/specialist-business \
  --set startupProbe.failureThreshold=60 \
  -n neural-hive-specialists
```

---

## 4. Liveness & Readiness Probes

### Liveness Probe

**Purpose:** Detect if the container is deadlocked/crashed and needs restart

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 60   # Start AFTER startup probe succeeds
  periodSeconds: 30         # Check every 30s
  timeoutSeconds: 10        # Each check has 10s timeout
  failureThreshold: 3       # 3 failures = 90s before restart
```

**When Triggered:**
- Application hangs/deadlocks
- Infinite loop in code
- Database connection pool exhausted

---

### Readiness Probe

**Purpose:** Detect if the container is ready to serve traffic

```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 30   # Start checking after 30s
  periodSeconds: 10         # Check every 10s
  timeoutSeconds: 5         # Each check has 5s timeout
  failureThreshold: 3       # 3 failures = 30s before removing from service
```

**When Triggered:**
- Dependencies unavailable (circuit breakers open)
- Overloaded (high request queue)
- Warm-up not complete

---

### When to Adjust

#### Increase Liveness `failureThreshold` If:

**Symptom:** Pods restart during temporary dependency outages

```bash
# Check restart reasons
kubectl describe pod <pod-name> | grep -A 10 "Last State"

# If seeing frequent restarts due to liveness
kubectl get pods -n neural-hive-specialists \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.containerStatuses[0].restartCount}{"\n"}{end}'
```

**Solution:**
```yaml
livenessProbe:
  failureThreshold: 5       # 5 * 30s = 150s tolerance
```

---

#### Increase Readiness `failureThreshold` If:

**Symptom:** Pods removed from service too quickly during load spikes

```bash
# Check service endpoints flapping
kubectl get endpoints -n neural-hive-specialists -w

# Check readiness failures
kubectl describe pod <pod-name> | grep "Readiness probe failed"
```

**Solution:**
```yaml
readinessProbe:
  failureThreshold: 5       # 5 * 10s = 50s tolerance
```

---

## 5. Pod Anti-Affinity

### Current Configuration (Soft)

```yaml
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:  # SOFT
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchExpressions:
              - key: app.kubernetes.io/name
                operator: In
                values:
                  - specialist-business
          topologyKey: topology.kubernetes.io/zone
```

### Why SOFT (Preferred) Not HARD (Required)

**Advantages:**
- ✅ Allows scheduling even if anti-affinity can't be satisfied
- ✅ Prevents Pending pods in small clusters
- ✅ Still tries to spread pods across zones when possible
- ✅ Graceful degradation if zones are unavailable

**Trade-offs:**
- ⚠️ Multiple pods may land on same zone if capacity limited
- ⚠️ Reduced availability if zone fails

---

### When to Use HARD Anti-Affinity

**Use Case:** Production with multiple availability zones and strict HA requirements

```yaml
affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:  # HARD
      - labelSelector:
          matchExpressions:
            - key: app.kubernetes.io/name
              operator: In
              values:
                - specialist-business
        topologyKey: topology.kubernetes.io/zone
```

**Requirements:**
- Cluster has 3+ zones with capacity
- High availability is mandatory
- Can tolerate Pending pods if zones unavailable

---

### When to Keep SOFT Anti-Affinity

**Use Case:** Development, staging, or cost-optimized production

```yaml
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:  # SOFT (current)
      - weight: 100
        # ... existing config
```

**When to use:**
- Cluster has <3 zones
- Limited node capacity
- Cost optimization is priority
- Can tolerate zone failure risk

---

## 6. Troubleshooting Decision Tree

```
Pod Status Check
├─ CrashLoopBackOff?
│  ├─ Check logs for error
│  │  ├─ "Startup probe failed"
│  │  │  └─ Solution: Increase startupProbe.failureThreshold
│  │  ├─ "OOMKilled"
│  │  │  └─ Solution: Increase memory requests/limits
│  │  ├─ "MongoDB connection failed"
│  │  │  └─ Solution: Check MongoDB availability, enable graceful degradation
│  │  └─ Other error
│  │     └─ See DIAGNOSTIC_PODS_CRASHLOOP.md
│  └─ kubectl logs <pod> --previous
│
├─ Pending?
│  ├─ Check events
│  │  ├─ "Insufficient cpu"
│  │  │  └─ Solution: Reduce CPU requests OR scale cluster
│  │  ├─ "Insufficient memory"
│  │  │  └─ Solution: Reduce memory requests OR scale cluster
│  │  ├─ "MatchNodeSelector"
│  │  │  └─ Solution: Check node labels and selectors
│  │  └─ "PodAntiAffinity"
│  │     └─ Solution: Change to soft anti-affinity OR add nodes
│  └─ kubectl describe pod <pod>
│
└─ Running but not Ready?
   ├─ Check readiness probe
   │  ├─ kubectl describe pod <pod> | grep Readiness
   │  └─ kubectl exec <pod> -- curl http://localhost:8000/ready
   ├─ Check dependency health
   │  └─ kubectl logs <pod> | grep -i "unavailable\|unhealthy"
   └─ Check circuit breaker states
      └─ kubectl logs <pod> | grep "circuit_breaker"
```

---

## 7. Example Configurations

### Example 1: Minimal Resources (Dev Laptop)

**Use Case:** Local development on MacBook or Linux workstation

```yaml
# File: my-dev-overrides.yaml
replicaCount: 1

resources:
  requests:
    cpu: 100m       # Very low for laptop
    memory: 256Mi   # Minimal memory
  limits:
    cpu: 500m
    memory: 1Gi

startupProbe:
  failureThreshold: 60  # Very generous (10 minutes)

config:
  ledgerRequired: false  # Graceful degradation
  logLevel: DEBUG

# Disable anti-affinity for single node
affinity: {}
```

**Deploy:**
```bash
helm upgrade specialist-business ./helm-charts/specialist-business \
  -f my-dev-overrides.yaml \
  -n neural-hive-specialists
```

---

### Example 2: Production HA

**Use Case:** Production with SLA guarantees and multiple zones

```yaml
# File: prod-ha-overrides.yaml
replicaCount: 3

resources:
  requests:
    cpu: 1          # High guaranteed resources
    memory: 2Gi
  limits:
    cpu: 4
    memory: 8Gi

startupProbe:
  failureThreshold: 20  # Fast startup expected

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 20
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80

affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:  # HARD
      - labelSelector:
          matchExpressions:
            - key: app.kubernetes.io/name
              operator: In
              values:
                - specialist-business
        topologyKey: topology.kubernetes.io/zone

config:
  ledgerRequired: true  # Fail-fast for compliance
```

**Deploy:**
```bash
helm upgrade specialist-business ./helm-charts/specialist-business \
  -f environments/prod/helm-values/specialist-business-values.yaml \
  -f prod-ha-overrides.yaml \
  -n neural-hive-specialists
```

---

### Example 3: Cost-Optimized Cloud

**Use Case:** Production in cloud with cost constraints

```yaml
# File: cost-optimized-overrides.yaml
replicaCount: 2

resources:
  requests:
    cpu: 250m       # Low requests for better bin-packing
    memory: 512Mi
  limits:
    cpu: 1          # Modest limits
    memory: 2Gi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 80  # Higher target for cost savings
  targetMemoryUtilizationPercentage: 85

# Use spot instances
tolerations:
  - key: "node.kubernetes.io/instance-type"
    operator: "Equal"
    value: "spot"
    effect: "NoSchedule"

nodeSelector:
  node.kubernetes.io/instance-type: spot

config:
  ledgerRequired: false  # Graceful degradation for resilience
```

**Deploy:**
```bash
helm upgrade specialist-business ./helm-charts/specialist-business \
  -f cost-optimized-overrides.yaml \
  -n neural-hive-specialists
```

---

## 8. Capacity Planning

### Estimating Resource Needs

**Formula:**
```
Total CPU = (base CPU + model inference CPU) × concurrency × safety margin
Total Memory = (base memory + model size + cache) × safety margin
```

**Example Calculation for specialist-business:**

```
Base CPU: 100m (application overhead)
Model inference: 200m per evaluation
Expected concurrency: 5 concurrent evaluations
Safety margin: 1.5x

Total CPU request = (100m + 200m) × 5 × 1.5 = 2250m = 2.25 cores
→ Set request to 2 cores, limit to 4 cores for burst

Base Memory: 200Mi (application)
Model size: 300Mi (loaded model)
Cache: 100Mi (opinion cache)
Safety margin: 1.5x

Total Memory request = (200Mi + 300Mi + 100Mi) × 1.5 = 900Mi
→ Set request to 1Gi, limit to 2Gi for burst
```

---

### Cluster Capacity Planning

**Per-Specialist Requirements (Production):**
```
CPU: 500m request, 2 cores limit
Memory: 1Gi request, 4Gi limit
Pods per specialist: 2-3 replicas
```

**Cluster Needs for All 5 Specialists:**
```
Total CPU: 500m × 5 specialists × 2 replicas = 5 cores (requests)
Total Memory: 1Gi × 5 specialists × 2 replicas = 10Gi (requests)

With overhead (system pods, networking):
Minimum cluster: 8 cores, 16Gi RAM (tight)
Recommended cluster: 12 cores, 24Gi RAM (comfortable)
Production cluster: 16-24 cores, 32-48Gi RAM (HA + headroom)
```

---

## 9. Performance Optimization

### Baseline Performance Metrics

**Target Metrics (Production):**
```
Startup Time: <3 minutes
P50 Latency: <200ms
P95 Latency: <500ms
P99 Latency: <1s
Throughput: 10-20 evaluations/sec per pod
CPU Utilization: 40-60% (allows burst)
Memory Utilization: 50-70% (stable)
```

### Optimization Checklist

**CPU Optimization:**
- [ ] Model is using optimized BLAS (OpenBLAS, MKL)
- [ ] Model is serialized efficiently (joblib, pickle protocol 5)
- [ ] Unnecessary logging is disabled in hot paths
- [ ] Connection pooling is enabled for databases
- [ ] Thread pool size matches CPU limit

**Memory Optimization:**
- [ ] Models are loaded once and cached
- [ ] Feature vectors are not copied unnecessarily
- [ ] Large objects are released after use
- [ ] Opinion cache has TTL to prevent unbounded growth
- [ ] Garbage collection is tuned for workload

**I/O Optimization:**
- [ ] Model files are on fast storage (local SSD > EBS > EFS)
- [ ] Database queries use indexes
- [ ] Connection pools are sized correctly
- [ ] Circuit breakers prevent slow dependency cascades

---

## 10. Related Documentation

- [GRACEFUL_DEGRADATION_GUIDE.md](./GRACEFUL_DEGRADATION_GUIDE.md) - Handling dependency failures
- [DIAGNOSTIC_PODS_CRASHLOOP.md](../DIAGNOSTIC_PODS_CRASHLOOP.md) - Troubleshooting pod crashes
- [REMEDIATION_GUIDE_PODS.md](../REMEDIATION_GUIDE_PODS.md) - Step-by-step remediation procedures
- [Kubernetes Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Kubernetes Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)

---

**Last Updated:** 2025-01-10
**Version:** 1.0
**Authors:** Neural Hive Mind Team
