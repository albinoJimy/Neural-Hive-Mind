# Remediation Guide: Pods in CrashLoop/Pending States

## Executive Summary

This guide documents the complete process to fix specialists in CrashLoop/Pending states within the Neural Hive Mind cluster.

**Root Causes Identified:**
1. Missing `structlog` dependency in Docker images (Critical)
2. Resource constraints - cluster at 94% CPU utilization (High Priority)
3. Aggressive health check timing without startup probes (Medium Priority)
4. Complex dependencies requiring longer initialization time
5. LedgerClient initialization without graceful degradation (Critical - FIXED)
6. Missing retry logic in MongoDB connection (High Priority - FIXED)

**Solution Approach:**
- Rebuild images with missing dependencies
- Add startup probes to handle slow initialization
- Optimize resource allocations for dev environment
- Incremental rollout with validation at each step
- Implement graceful degradation for LedgerClient
- Add retry logic with exponential backoff for MongoDB
- Add configuration flags for fail-fast vs fail-gracefully modes

**Estimated Time to Resolution:** 1.5 - 2.5 hours

---

## Prerequisites

### Required Tools
- `kubectl` (configured with cluster access)
- `docker` (with daemon running)
- `helm` (optional, for helm-based deployments)
- `curl` (for API testing)

### Required Access
- Kubernetes cluster admin permissions
- Access to local Docker registry (localhost:5000)
- Sufficient disk space (10GB minimum for image builds)

### Required Resources
- Cluster capacity for rolling updates
- Backup storage for current configurations

---

## Phase 1: Diagnostic Collection (15 minutes)

### Step 1.1: Run Diagnostic Script

Execute the automated diagnostic collection script:

```bash
./scripts/diagnostics/collect-pod-diagnostics.sh
```

**What it does:**
- Lists all pods and their status
- Identifies pods in problematic states (CrashLoop, Pending, ImagePullBackOff)
- Collects logs from failed containers
- Analyzes cluster resource utilization
- Checks dependency health
- Generates summary report

**Expected Output:**
```
=== Neural Hive Mind - Pod Diagnostics Collection ===
[1/8] Collecting cluster overview...
[2/8] Collecting pod status...
[3/8] Collecting details from problematic pods...
...
=== Diagnostic Collection Complete ===
```

**Review the summary report:**
```bash
cat logs/diagnostics-<timestamp>/SUMMARY.md
```

### Step 1.2: Analyze Root Causes

Review the diagnostic report to identify:

1. **Image Issues:**
   - Missing structlog dependency → Rebuild images needed
   - Image pull failures → Check registry availability

2. **Resource Constraints:**
   - CPU usage > 90% → Reduce resource requests or scale cluster
   - Memory pressure → Adjust limits or add nodes

3. **Configuration Errors:**
   - Missing ConfigMaps/Secrets → Create required configurations
   - Invalid environment variables → Fix configuration

4. **Dependency Failures:**
   - MongoDB/MLflow/Neo4j/Redis unavailable → Fix dependencies first
   - Network connectivity issues → Check services and DNS

5. **Health Check Failures:**
   - Pods killed before fully started → Add startup probes (covered in Phase 3)
   - Aggressive timeouts → Increase health check delays

### Step 1.3: Verify Prerequisites

Before proceeding, ensure:

```bash
# Check Docker is running
docker info

# Check registry is accessible
curl http://localhost:5000/v2/_catalog

# Check cluster resources
kubectl top nodes

# Check dependencies are healthy
kubectl get pods -n neural-hive-specialists -l app=mongodb
kubectl get pods -n neural-hive-specialists -l app=mlflow
kubectl get pods -n neural-hive-specialists -l app=neo4j
kubectl get pods -n neural-hive-specialists -l app=redis
```

---

## Phase 2: Image Rebuild (30-60 minutes)

### Step 2.1: Verify Code Changes

Confirm that `structlog` is in all requirements.txt files:

```bash
grep -r "structlog" services/specialist-*/requirements.txt
```

**Expected output:**
```
services/specialist-business/requirements.txt:structlog==23.1.0
services/specialist-technical/requirements.txt:structlog==23.1.0
services/specialist-behavior/requirements.txt:structlog==23.1.0
services/specialist-evolution/requirements.txt:structlog==23.1.0
services/specialist-architecture/requirements.txt:structlog==23.1.0
```

If any are missing, add `structlog==23.1.0` to the respective requirements.txt file.

### Step 2.2: Rebuild Images

Execute the image rebuild script:

**Sequential Mode (Recommended - Safer):**
```bash
./scripts/remediation/rebuild-specialist-images.sh --sequential --version v1.0.10
```

**Parallel Mode (Faster but riskier):**
```bash
./scripts/remediation/rebuild-specialist-images.sh --parallel --version v1.0.10
```

**Options:**
- `--version`: Specify version tag (default: v1.0.10)
- `--sequential`: Build one at a time (default)
- `--parallel`: Build all simultaneously
- `--dry-run`: Preview what would be built
- `--cleanup`: Remove old images after successful build

**Expected Output:**
```
=== Neural Hive Mind - Specialist Image Rebuild ===
[Pre-flight] Running pre-flight checks...
✅ Docker daemon is running
✅ Sufficient disk space: 50GB available
✅ Registry localhost:5000 is accessible
✅ All requirements.txt files contain structlog

[Build] Starting sequential build...

Building specialist-business...
✅ Build successful: specialist-business (120s, 1.2GB)
✅ Push successful: localhost:5000/specialist-business:v1.0.10
✅ structlog verified in specialist-business

Building specialist-technical...
...
```

### Step 2.3: Validate Images

Verify all images were built successfully:

```bash
# Check images in local Docker
docker images | grep specialist

# Check images in registry
curl http://localhost:5000/v2/specialist-business/tags/list
curl http://localhost:5000/v2/specialist-technical/tags/list
curl http://localhost:5000/v2/specialist-behavior/tags/list
curl http://localhost:5000/v2/specialist-evolution/tags/list
curl http://localhost:5000/v2/specialist-architecture/tags/list
```

**Test structlog import:**
```bash
docker run --rm localhost:5000/specialist-business:v1.0.10 python -c "import structlog; print('OK')"
```

---

## Phase 3: Configuration Updates (15 minutes)

### Step 3.1: Verify Helm Chart Updates

The helm charts have been updated with startup probe configurations. Verify the changes:

```bash
# Check deployment templates
grep -A 5 "startupProbe" helm-charts/specialist-business/templates/deployment.yaml

# Check values files
grep -A 10 "startupProbe" helm-charts/specialist-business/values.yaml

# Check dev environment overrides
grep -A 10 "startupProbe" environments/dev/helm-values/specialist-business-values.yaml
```

**Startup Probe Configuration:**
- **Production (values.yaml):** 5 minutes max startup time (30 failures × 10s)
- **Dev (dev values):** 10 minutes max startup time (40 failures × 15s)

### Step 3.2: Review Resource Adjustments (Optional)

Dev environment resource requests have been optimized:

**Before:**
```yaml
resources:
  requests:
    cpu: 200m
    memory: 512Mi
```

**After:**
```yaml
resources:
  requests:
    cpu: 250m      # Slightly increased for better performance
    memory: 512Mi
```

If cluster is still resource-constrained, consider:

1. **Reduce replicas temporarily:**
   ```bash
   kubectl scale deployment specialist-business -n neural-hive-specialists --replicas=1
   ```

2. **Scale down non-critical services:**
   ```bash
   # Example: scale down monitoring
   kubectl scale deployment prometheus -n observability --replicas=0
   ```

3. **Add cluster nodes** (if using managed Kubernetes)

### Step 3.3: Validate Configurations

Dry-run helm upgrades to check for errors:

```bash
helm upgrade specialist-business ./helm-charts/specialist-business \
  -f environments/dev/helm-values/specialist-business-values.yaml \
  -n neural-hive-specialists \
  --dry-run --debug
```

Check for:
- YAML syntax errors
- Missing required values
- Invalid configurations

---

## Phase 4: Deployment Updates (20-30 minutes)

### Step 4.1: Backup Current State

Backups are created automatically by the update script, but you can manually backup:

```bash
# Backup deployments
kubectl get deployments -n neural-hive-specialists -o yaml > backup-deployments.yaml

# Backup current pod logs
for pod in $(kubectl get pods -n neural-hive-specialists -o name); do
  kubectl logs $pod > backup-logs-$(echo $pod | cut -d/ -f2).txt
done
```

### Step 4.2: Execute Updates

**Incremental Mode (Recommended):**
```bash
./scripts/remediation/update-specialist-deployments.sh \
  --incremental \
  --version v1.0.10 \
  --namespace neural-hive-specialists
```

**What it does:**
1. Updates one specialist at a time
2. Waits for each to be healthy before proceeding
3. Monitors rollout progress
4. Checks logs for errors
5. Prompts before continuing if failures occur

**Expected Output:**
```
=== Neural Hive Mind - Specialist Deployments Update ===
[Phase 1] Running pre-update validation...
✅ kubectl available
✅ Namespace neural-hive-specialists exists
✅ All images available in registry

[Phase 2] Backing up current deployment state...
✅ Backup complete

[Phase 3] Executing deployment updates (incremental mode)...

Updating specialist-business...
  Setting image to localhost:5000/specialist-business:v1.0.10...
✅ Image updated
  Monitoring rollout progress...
✅ Rollout successful (45s)
✅ All pods ready (1/1)
✅ No errors in logs

Updating specialist-technical...
...
```

**Parallel Mode (Faster but riskier):**
```bash
./scripts/remediation/update-specialist-deployments.sh \
  --parallel \
  --version v1.0.10
```

Use only if confident in changes and need faster deployment.

### Step 4.3: Handle Failures

If any specialist fails to update:

1. **Check the logs:**
   ```bash
   kubectl logs -n neural-hive-specialists -l app=specialist-business --tail=100
   kubectl describe pod -n neural-hive-specialists -l app=specialist-business
   ```

2. **Common issues:**
   - **Image pull failed:** Verify image exists in registry
   - **Pod crash:** Check logs for application errors
   - **Startup timeout:** Increase startup probe failureThreshold
   - **Resource limits:** Check if pod is OOMKilled

3. **Rollback if needed:**
   ```bash
   # Rollback to previous version
   kubectl rollout undo deployment/specialist-business -n neural-hive-specialists

   # Or restore from backup
   kubectl apply -f logs/deployment-update-*/backups/specialist-business-deployment.yaml
   ```

4. **Fix and retry:**
   - Address the specific issue
   - Re-run the update script
   - Use `--skip-validation` if already validated

---

## Phase 5: Validation (15 minutes)

### Step 5.1: Run Health Validation

Execute the comprehensive health validation script:

```bash
./scripts/validation/validate-specialist-health.sh --verbose
```

**What it validates:**
1. **Pod Status:** Running, Ready, Low restart count
2. **Container Health:** No OOM, resource usage within limits
3. **Logs:** No structlog errors, startup messages present
4. **Endpoints:** Health, ready, metrics, gRPC endpoints responding
5. **Dependencies:** MongoDB, MLflow, Neo4j, Redis reachable
6. **Resources:** Usage below limits
7. **Configuration:** Correct images, startup probes configured
8. **Integration:** (Optional) End-to-end tests

**Expected Output:**
```
=== Specialist Health Validation ===

[1/8] Validating pod status...

  specialist-business:
✅ Pod Status: Running
✅ Ready Status: 1/1
✅ Restart Count: 0

  specialist-technical:
✅ Pod Status: Running
✅ Ready Status: 1/1
✅ Restart Count: 0

...

[8/8] Running integration tests...
  (Skipped with --skip-integration)

=== Validation Summary ===
Total Checks: 40
Passed: 40
Failed: 0
Warnings: 0

✅ All specialists are healthy!
```

### Step 5.2: Monitor Stability

Monitor pods for 5-10 minutes to ensure stability:

```bash
# Watch pod status
watch kubectl get pods -n neural-hive-specialists

# Monitor logs in real-time
kubectl logs -f -n neural-hive-specialists -l app=specialist-business

# Check restart counts
kubectl get pods -n neural-hive-specialists -o custom-columns=NAME:.metadata.name,RESTARTS:.status.containerStatuses[0].restartCount
```

**What to watch for:**
- Restart counts should remain at 0
- No CrashLoopBackOff
- Resource usage stable
- No error messages in logs

### Step 5.3: End-to-End Testing

Test the complete intention flow:

```bash
# Send test request to gateway
curl -X POST http://gateway-intencoes.neural-hive-specialists.svc.cluster.local:8080/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Analisar riscos do projeto X",
    "user_id": "test-user-123",
    "context": {}
  }'
```

**Verify:**
- Gateway receives and processes request
- Semantic Translation Engine creates plan
- All specialists are consulted
- Consensus Engine aggregates opinions
- Response is returned successfully

---

## Phase 6: Cleanup and Documentation (10 minutes)

### Step 6.1: Clean Up Old Resources

**Remove old Docker images (optional):**
```bash
# Remove old specialist images
docker images | grep specialist | grep -v v1.0.10 | awk '{print $3}' | xargs docker rmi

# Remove dangling images
docker image prune -f
```

**Clean up diagnostic files (optional):**
```bash
# Keep only recent diagnostics
find logs/diagnostics-* -type d -mtime +7 -exec rm -rf {} \;
```

### Step 6.2: Update Documentation

Document the changes made:

1. **Update deployment log:**
   ```bash
   echo "$(date): Deployed v1.0.10 with startup probes and structlog fix" >> DEPLOYMENT_LOG.md
   ```

2. **Update version tracking:**
   ```bash
   # Update helm chart versions if needed
   # Commit changes to git
   git add helm-charts/specialist-*/Chart.yaml
   git commit -m "chore: bump specialist versions to 1.0.10"
   ```

3. **Record lessons learned:**
   - Document root causes
   - Note any unexpected issues
   - Update runbooks with new procedures

### Step 6.3: Post-Mortem

Conduct a brief post-mortem:

**What went well:**
- Automated scripts made remediation faster
- Startup probes prevented premature restarts
- Incremental rollout allowed early issue detection

**What could be improved:**
- Earlier detection of missing dependencies (add to CI/CD)
- Better initial resource allocation
- More comprehensive health checks in development

**Preventive Measures:**
1. **Add dependency checks to Dockerfile build:**
   ```dockerfile
   # Verify critical dependencies
   RUN python -c "import structlog"
   ```

2. **Add pre-deployment validation:**
   - Check images have required dependencies
   - Validate resource availability
   - Test health endpoints before rollout

3. **Improve monitoring:**
   - Alert on high restart counts
   - Monitor startup times
   - Track resource pressure conditions

4. **Update CI/CD pipeline:**
   - Add integration tests
   - Validate container startup
   - Check dependency availability

---

## Troubleshooting Common Issues

### Issue: Build Fails with Disk Space Error

**Symptoms:**
```
Error: No space left on device
```

**Solution:**
```bash
# Clean Docker cache
docker system prune -a -f

# Remove old images
docker images | grep '<none>' | awk '{print $3}' | xargs docker rmi

# Check available space
df -h
```

### Issue: Pod Still Crashes After Image Update

**Symptoms:**
- Pod goes to CrashLoopBackOff despite new image
- Restart count increases

**Solution:**
1. **Check logs for actual error:**
   ```bash
   kubectl logs <pod-name> -n neural-hive-specialists --previous
   ```

2. **Verify structlog is installed:**
   ```bash
   kubectl exec <pod-name> -n neural-hive-specialists -- python -c "import structlog"
   ```

3. **Check for other missing dependencies:**
   ```bash
   kubectl logs <pod-name> -n neural-hive-specialists | grep "ModuleNotFoundError\|ImportError"
   ```

4. **Verify environment variables:**
   ```bash
   kubectl exec <pod-name> -n neural-hive-specialists -- env | grep -E "MONGODB|MLFLOW|NEO4J|REDIS"
   ```

### Issue: Startup Probe Times Out

**Symptoms:**
```
Warning  Unhealthy  Pod  Startup probe failed
```

**Solution:**
1. **Check actual startup time:**
   ```bash
   kubectl logs <pod-name> -n neural-hive-specialists | grep "started"
   ```

2. **Increase failureThreshold if startup is legitimately slow:**
   ```yaml
   startupProbe:
     failureThreshold: 60  # 60 * 10s = 10 minutes
   ```

3. **Check what's causing slow startup:**
   - Large ML model loading → Consider model caching
   - Slow dependency connections → Verify network
   - Initialization logic → Profile and optimize

### Issue: Cluster Has Insufficient Resources

**Symptoms:**
```
0/3 nodes are available: 3 Insufficient cpu.
```

**Solution:**
1. **Scale down non-critical services:**
   ```bash
   kubectl scale deployment <non-critical-app> --replicas=0
   ```

2. **Reduce resource requests temporarily:**
   ```yaml
   resources:
     requests:
       cpu: 100m  # Reduced from 250m
   ```

3. **Add cluster nodes** (managed Kubernetes)

4. **Use resource quotas and limits:**
   ```bash
   kubectl describe resourcequota -n neural-hive-specialists
   ```

### Issue: Image Pull Fails

**Symptoms:**
```
Failed to pull image: Error response from daemon: manifest not found
```

**Solution:**
1. **Verify image exists:**
   ```bash
   curl http://localhost:5000/v2/specialist-business/tags/list
   ```

2. **Check image name in deployment:**
   ```bash
   kubectl get deployment specialist-business -n neural-hive-specialists -o jsonpath='{.spec.template.spec.containers[0].image}'
   ```

3. **Rebuild missing image:**
   ```bash
   ./scripts/remediation/rebuild-specialist-images.sh --version v1.0.10
   ```

4. **Check registry accessibility from cluster:**
   ```bash
   kubectl run test --rm -it --image=curlimages/curl -- curl http://localhost:5000/v2/_catalog
   ```

---

## Rollback Procedures

### Rollback Single Deployment

```bash
# Rollback to previous version
kubectl rollout undo deployment/specialist-business -n neural-hive-specialists

# Rollback to specific revision
kubectl rollout undo deployment/specialist-business -n neural-hive-specialists --to-revision=2

# Check rollout history
kubectl rollout history deployment/specialist-business -n neural-hive-specialists
```

### Rollback All Deployments

```bash
# Rollback all specialists
for specialist in specialist-business specialist-technical specialist-behavior specialist-evolution specialist-architecture; do
  kubectl rollout undo deployment/$specialist -n neural-hive-specialists
done
```

### Restore from Backup

```bash
# Restore specific deployment
kubectl apply -f logs/deployment-update-*/backups/specialist-business-deployment.yaml

# Restore all deployments
kubectl apply -f logs/deployment-update-*/backups/
```

### Remove Startup Probes (If Causing Issues)

```bash
# Remove startup probe from deployment
kubectl patch deployment specialist-business -n neural-hive-specialists \
  --type json \
  -p='[{"op": "remove", "path": "/spec/template/spec/containers/0/startupProbe"}]'
```

---

## Success Criteria

Verify all criteria before considering remediation complete:

- ✅ All 5 specialists in Running state (1/1 Ready)
- ✅ Restart counts are 0 or very low (< 3)
- ✅ No structlog errors in logs
- ✅ All health checks passing (startup, liveness, readiness)
- ✅ Dependencies reachable from all specialists
- ✅ Resource usage within limits (no OOM, no throttling)
- ✅ End-to-end tests passing
- ✅ System stable for 10+ minutes

**Verification commands:**
```bash
# Quick health check
kubectl get pods -n neural-hive-specialists
kubectl get deployments -n neural-hive-specialists

# Detailed validation
./scripts/validation/validate-specialist-health.sh
```

---

## Estimated Timeline

| Phase | Duration | Cumulative |
|-------|----------|------------|
| Diagnostic Collection | 15 min | 15 min |
| Image Rebuild (Sequential) | 30-60 min | 45-75 min |
| Configuration Updates | 15 min | 60-90 min |
| Deployment Updates | 20-30 min | 80-120 min |
| Validation | 15 min | 95-135 min |
| Cleanup | 10 min | 105-145 min |

**Total: 1.5 - 2.5 hours**

*Note: Parallel builds can reduce time to 1.5-2 hours total.*

---

## Contact and Escalation

If issues persist after following this guide:

1. **Check existing documentation:**
   - `docs/operations/troubleshooting-guide.md`
   - `docs/SPECIALIST-FIX-GUIDE.md`
   - `DIAGNOSTIC_PODS_CRASHLOOP.md`

2. **Gather diagnostic information:**
   ```bash
   ./scripts/diagnostics/collect-pod-diagnostics.sh
   ```

3. **Escalate with context:**
   - Provide diagnostic report
   - Include pod logs
   - Describe steps already taken
   - Specify any error messages

4. **Escalation paths:**
   - **Infrastructure issues:** Platform/DevOps team
   - **Application issues:** Development team
   - **Dependency issues:** Data infrastructure team

---

## Phase 6: Graceful Degradation Validation (10 minutes)

This phase validates the new graceful degradation features that allow specialists to start and operate even when dependencies (MongoDB, MLflow, Redis) are unavailable.

### Step 6.1: Test Degraded Mode

Simulate MongoDB unavailable to verify specialists can still start and operate:

```bash
# Scale down MongoDB
kubectl scale statefulset mongodb -n mongodb-cluster --replicas=0

# Wait for MongoDB to terminate
kubectl wait --for=delete pod -l app=mongodb -n mongodb-cluster --timeout=60s

# Wait for specialists to detect failure
sleep 30

# Check specialist pods are still Running (not CrashLoopBackOff)
kubectl get pods -n neural-hive-specialists

# Expected output: All pods should be Running
# NAME                                     READY   STATUS    RESTARTS   AGE
# specialist-business-xxx                  1/1     Running   0          5m
# specialist-technical-xxx                 1/1     Running   0          5m
# ...
```

**Check health endpoint shows degraded status:**

```bash
# Get pod name
POD_NAME=$(kubectl get pods -n neural-hive-specialists -l app.kubernetes.io/name=specialist-business -o jsonpath='{.items[0].metadata.name}')

# Check ready endpoint
kubectl exec -n neural-hive-specialists $POD_NAME -- curl -s http://localhost:8000/ready | jq

# Expected output:
# {
#   "ready": true,
#   "specialist_type": "business",
#   "degraded": true,
#   "degraded_reasons": ["ledger_unavailable"],
#   "details": {
#     "ledger": "unavailable",
#     "mlflow": "healthy",
#     "opinion_cache": "healthy"
#   }
# }
```

**Check logs show graceful degradation:**

```bash
kubectl logs -n neural-hive-specialists $POD_NAME | grep -i "ledger" | tail -10

# Expected log messages:
# Ledger client unavailable - continuing without ledger persistence
# Ledger unavailable - opinion not persisted
# Operating in degraded mode: ledger_unavailable
```

**Validation Criteria:**
- ✅ Pods are Running (not CrashLoopBackOff)
- ✅ Health endpoint returns `ready: true` and `degraded: true`
- ✅ Logs show graceful degradation messages
- ✅ `degraded_reasons` includes "ledger_unavailable"

---

### Step 6.2: Verify Automatic Recovery

Test that specialists automatically recover when MongoDB becomes available:

```bash
# Scale up MongoDB
kubectl scale statefulset mongodb -n mongodb-cluster --replicas=1

# Wait for MongoDB to be ready
kubectl wait --for=condition=ready pod -l app=mongodb -n mongodb-cluster --timeout=120s

# Verify MongoDB is healthy
kubectl exec -n mongodb-cluster mongodb-0 -- mongosh --eval "db.adminCommand('ping')"

# Wait for circuit breaker recovery (60s default timeout)
echo "Waiting 70 seconds for circuit breaker recovery..."
sleep 70

# Check specialists recovered
POD_NAME=$(kubectl get pods -n neural-hive-specialists -l app.kubernetes.io/name=specialist-business -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n neural-hive-specialists $POD_NAME -- curl -s http://localhost:8000/ready | jq

# Expected: degraded should be false or degraded_reasons should not include ledger_unavailable
# {
#   "ready": true,
#   "degraded": false,
#   "details": {
#     "ledger": "healthy",
#     "ledger_connected": "True"
#   }
# }
```

**Check logs show recovery:**

```bash
kubectl logs -n neural-hive-specialists $POD_NAME --since=2m | grep -i "ledger\|circuit"

# Expected log messages:
# Circuit breaker half-open, attempting recovery
# MongoDB connection established
# Circuit breaker closed, ledger_client recovered
# Ledger indexes created successfully
```

**Validation Criteria:**
- ✅ MongoDB is healthy and accepting connections
- ✅ Health endpoint returns `degraded: false`
- ✅ `ledger` status is "healthy" or "connected"
- ✅ Logs show circuit breaker recovery
- ✅ No new error messages in logs

---

### Step 6.3: Test Fail-Fast Mode

Verify that fail-fast mode works correctly when `ledgerRequired=true`:

```bash
# Update specialist-business to require ledger
helm upgrade specialist-business ./helm-charts/specialist-business \
  --set config.ledgerRequired=true \
  -f environments/dev/helm-values/specialist-business-values.yaml \
  -n neural-hive-specialists

# Wait for rollout
kubectl rollout status deployment/specialist-business -n neural-hive-specialists

# Scale down MongoDB again
kubectl scale statefulset mongodb -n mongodb-cluster --replicas=0

# Delete specialist pod to force restart
kubectl delete pod -l app.kubernetes.io/name=specialist-business -n neural-hive-specialists

# Wait a bit for pod to attempt startup
sleep 30

# Verify pod crashes (CrashLoopBackOff)
kubectl get pods -n neural-hive-specialists -l app.kubernetes.io/name=specialist-business

# Expected output:
# NAME                                  READY   STATUS             RESTARTS   AGE
# specialist-business-xxx               0/1     CrashLoopBackOff   2          1m
```

**Check logs show fatal error:**

```bash
POD_NAME=$(kubectl get pods -n neural-hive-specialists -l app.kubernetes.io/name=specialist-business -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n neural-hive-specialists $POD_NAME --tail=50

# Expected: Logs should show ledger initialization failed and pod exited
# Failed to initialize ledger client (retry_attempt=true)
# All 5 retry attempts failed
# Ledger required but unavailable - cannot continue
```

**Restore graceful degradation mode:**

```bash
# Restore to graceful mode
helm upgrade specialist-business ./helm-charts/specialist-business \
  --set config.ledgerRequired=false \
  -f environments/dev/helm-values/specialist-business-values.yaml \
  -n neural-hive-specialists

# Scale up MongoDB
kubectl scale statefulset mongodb -n mongodb-cluster --replicas=1

# Wait for MongoDB
kubectl wait --for=condition=ready pod -l app=mongodb -n mongodb-cluster --timeout=120s

# Wait for specialist to recover
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=specialist-business -n neural-hive-specialists --timeout=300s

# Verify pod is healthy
kubectl get pods -n neural-hive-specialists -l app.kubernetes.io/name=specialist-business
```

**Validation Criteria:**
- ✅ With `ledgerRequired=true`, pod crashes when MongoDB unavailable
- ✅ Logs show "Ledger required but unavailable"
- ✅ With `ledgerRequired=false`, pod starts in degraded mode
- ✅ Pod automatically recovers when MongoDB is restored

---

### Step 6.4: Test Multiple Dependencies Degraded

Test combined degradation (MongoDB + MLflow unavailable):

```bash
# Scale down MongoDB and MLflow
kubectl scale statefulset mongodb -n mongodb-cluster --replicas=0
kubectl scale deployment mlflow -n mlflow --replicas=0

# Wait for termination
sleep 30

# Restart specialist pod
kubectl delete pod -l app.kubernetes.io/name=specialist-business -n neural-hive-specialists

# Wait for pod to start
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=specialist-business -n neural-hive-specialists --timeout=300s

# Check health endpoint
POD_NAME=$(kubectl get pods -n neural-hive-specialists -l app.kubernetes.io/name=specialist-business -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n neural-hive-specialists $POD_NAME -- curl -s http://localhost:8000/ready | jq

# Expected: Multiple degradation reasons
# {
#   "ready": true,
#   "degraded": true,
#   "degraded_reasons": ["ledger_unavailable", "mlflow_unavailable"],
#   "details": {
#     "ledger": "unavailable",
#     "mlflow_enabled": false
#   }
# }
```

**Restore all dependencies:**

```bash
# Scale up both
kubectl scale statefulset mongodb -n mongodb-cluster --replicas=1
kubectl scale deployment mlflow -n mlflow --replicas=1

# Wait for both
kubectl wait --for=condition=ready pod -l app=mongodb -n mongodb-cluster --timeout=120s
kubectl wait --for=condition=ready pod -l app=mlflow -n mlflow --timeout=120s

# Wait for circuit breaker recovery
sleep 70

# Verify full recovery
kubectl exec -n neural-hive-specialists $POD_NAME -- curl -s http://localhost:8000/ready | jq '.degraded'
# Expected: false
```

**Validation Criteria:**
- ✅ Pod starts with multiple dependencies unavailable
- ✅ `degraded_reasons` includes both "ledger_unavailable" and "mlflow_unavailable"
- ✅ Pod still functional (can evaluate plans with heuristics)
- ✅ Automatic recovery when all dependencies restored

---

### Step 6.5: Monitoring Degradation Metrics

Verify that degradation metrics are exposed correctly:

```bash
# Get metrics endpoint
POD_NAME=$(kubectl get pods -n neural-hive-specialists -l app.kubernetes.io/name=specialist-business -o jsonpath='{.items[0].metadata.name}')

# Fetch Prometheus metrics
kubectl exec -n neural-hive-specialists $POD_NAME -- curl -s http://localhost:8080/metrics | grep degraded

# Expected metrics:
# specialist_degraded_mode{component="ledger"} 1.0
# specialist_ledger_save_failures_total 15
# specialist_circuit_breaker_state{client="ledger"} 1
```

**Query metrics from Prometheus (if available):**

```bash
# Port-forward Prometheus
kubectl port-forward -n observability svc/prometheus 9090:9090 &

# Query degraded mode
curl -s 'http://localhost:9090/api/v1/query?query=specialist_degraded_mode' | jq

# Query save failures
curl -s 'http://localhost:9090/api/v1/query?query=rate(specialist_ledger_save_failures_total[5m])' | jq

# Stop port-forward
pkill -f "port-forward.*prometheus"
```

**Validation Criteria:**
- ✅ `specialist_degraded_mode` metric exposed
- ✅ Value is 1 when degraded, 0 when healthy
- ✅ `specialist_ledger_save_failures_total` tracks failed saves
- ✅ `specialist_circuit_breaker_state` tracks circuit breaker

---

### Phase 6 Summary

**What was validated:**
1. ✅ Graceful degradation works (pods start with MongoDB down)
2. ✅ Automatic recovery works (circuit breaker recovery)
3. ✅ Fail-fast mode works (pods crash when `ledgerRequired=true`)
4. ✅ Multiple dependencies can degrade simultaneously
5. ✅ Metrics are exposed for monitoring

**Key Improvements:**
- Specialists now resilient to MongoDB outages
- Circuit breaker provides automatic recovery
- Configuration allows choosing graceful vs fail-fast behavior
- Observable through logs, health endpoints, and metrics

**Next Steps:**
- Monitor degradation events in production
- Set up alerts for prolonged degradation (>5 minutes)
- Document runbooks for common degradation scenarios

---

## References

- **Diagnostic Guide:** `DIAGNOSTIC_PODS_CRASHLOOP.md`
- **Troubleshooting:** `docs/operations/troubleshooting-guide.md`
- **Specialist Fix Guide:** `docs/SPECIALIST-FIX-GUIDE.md`
- **Graceful Degradation Guide:** `docs/GRACEFUL_DEGRADATION_GUIDE.md`
- **Resource Tuning Guide:** `docs/RESOURCE_TUNING_GUIDE.md`
- **Kubernetes Probes:** https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
- **Resource Management:** https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/

---

**Document Version:** 1.0
**Last Updated:** 2025-11-10
**Author:** Neural Hive Mind DevOps Team
