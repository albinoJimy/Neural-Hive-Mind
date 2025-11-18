# Diagnostic Guide: Pods in CrashLoop/Pending States

## Overview

This guide provides step-by-step commands to diagnose pods in problematic states within the Neural Hive Mind cluster.

## Section 1: Quick Status Check

### List All Pods Across All Namespaces with Status
```bash
kubectl get pods -A -o wide
```

### Identify Pods in CrashLoopBackOff State

**IMPORTANT:** Field-selectors cannot detect CrashLoopBackOff because these pods often remain in `phase=Running` while the container state shows `waiting.reason=CrashLoopBackOff`. Always use JSON+jq filtering for accurate detection.

```bash
# PRIMARY METHOD: Using JSON+jq filtering (most accurate - RECOMMENDED)
kubectl get pods -A -o json | jq -r '
  .items[] |
  select(
    (.status.containerStatuses[]?.state.waiting.reason // "" | test("CrashLoopBackOff"))
  ) |
  "\(.metadata.namespace)\t\(.metadata.name)\t\(.status.phase)\t\(.status.containerStatuses[0].state.waiting.reason)\t\(.status.containerStatuses[0].restartCount)"
'

# Alternative: Using grep (UNRELIABLE - may miss pods in Running phase with CrashLoop state)
kubectl get pods -A | grep -i "CrashLoopBackOff"
```

**Why jq is required:** The `kubectl get pods` STATUS column shows "CrashLoopBackOff" only intermittently. Between restart attempts, the STATUS may show "Running" even though the container is waiting with reason "CrashLoopBackOff". The jq method checks the actual container state, not just the pod phase.

### Identify Pods in Pending State
```bash
kubectl get pods -A --field-selector=status.phase=Pending
```

### Identify Pods in ImagePullBackOff State
```bash
kubectl get pods -A | grep -i "ImagePullBackOff\|ErrImagePull"
```

### Identify Pods with High Restart Counts
```bash
# Using jq for better handling
kubectl get pods -A -o json | jq -r '.items[] | select(.status.containerStatuses[]?.restartCount > 5) | "\(.metadata.namespace)\t\(.metadata.name)\t\(.status.containerStatuses[0].restartCount)"'

# Alternative: Using jsonpath and awk
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.status.containerStatuses[0].restartCount}{"\n"}{end}' | awk '$3 > 5'
```

### Comprehensive Problematic Pod Detection (All Issues)

**RECOMMENDED:** Use this comprehensive jq query to detect ALL problematic pods regardless of phase:

```bash
kubectl get pods -n neural-hive-specialists -o json | jq -r '
  .items[] |
  select(
    (.status.phase != "Running" and .status.phase != "Succeeded") or
    (.status.containerStatuses[]?.state.waiting.reason // "" | test("CrashLoopBackOff|ImagePullBackOff|ErrImagePull")) or
    (.status.containerStatuses[]?.state.terminated.reason // "" | test("Error")) or
    (.status.containerStatuses[]?.restartCount // 0 > 3) or
    (.status.conditions[]? | select(.type == "Ready" or .type == "Initialized") | .status != "True")
  ) |
  [
    .metadata.name,
    .status.phase,
    (.status.containerStatuses[0].state.waiting.reason // .status.containerStatuses[0].state.terminated.reason // "N/A"),
    (.status.containerStatuses[0].restartCount // 0 | tostring)
  ] |
  @tsv
' | column -t
```

**This query detects:**
- Pods not in Running/Succeeded phase
- Pods with CrashLoopBackOff (even if phase=Running)
- Pods with ImagePullBackOff or ErrImagePull
- Pods with terminated containers showing errors
- Pods with excessive restarts (>3)
- Pods not meeting Ready/Initialized conditions

**Fallback without jq:**
```bash
kubectl get pods -n neural-hive-specialists -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,REASON:.status.containerStatuses[0].state.waiting.reason,RESTARTS:.status.containerStatuses[0].restartCount | awk 'NR==1 || ($2 !~ /Running|Succeeded/ || $3 ~ /CrashLoopBackOff|ImagePullBackOff|ErrImagePull/ || $4 > 3)'
```

### Example Output (Problematic)
```
NAMESPACE                 NAME                                         READY   STATUS             RESTARTS   AGE
neural-hive-specialists   specialist-business-7d8f9c5b6d-x7k2m        0/1     CrashLoopBackOff   15         30m
neural-hive-specialists   specialist-technical-6c9d8b5a7e-p3j9n       0/1     CrashLoopBackOff   12         30m
neural-hive-specialists   specialist-behavior-5b8c7a4d6f-m2h8k        0/1     Pending            0          30m
neural-hive-specialists   specialist-evolution-4a7b6c3e5d-n1g7j       0/1     CrashLoopBackOff   10         30m
neural-hive-specialists   specialist-architecture-3d6a5b2c4e-k4f6l    0/1     Pending            0          30m
```

### Example Output (Healthy)
```
NAMESPACE                 NAME                                         READY   STATUS    RESTARTS   AGE
neural-hive-specialists   specialist-business-7d8f9c5b6d-x7k2m        1/1     Running   0          10m
neural-hive-specialists   specialist-technical-6c9d8b5a7e-p3j9n       1/1     Running   0          10m
neural-hive-specialists   specialist-behavior-5b8c7a4d6f-m2h8k        1/1     Running   0          10m
neural-hive-specialists   specialist-evolution-4a7b6c3e5d-n1g7j       1/1     Running   0          10m
neural-hive-specialists   specialist-architecture-3d6a5b2c4e-k4f6l    1/1     Running   0          10m
```

## Section 2: Detailed Pod Diagnostics

For each problematic pod, run the following commands (replace `<pod-name>` and `<namespace>`):

### Get Pod Events and State Transitions
```bash
kubectl describe pod <pod-name> -n <namespace>
```

**Look for:**
- Events showing failures (e.g., "Back-off restarting failed container")
- Last State: Terminated (shows exit code and reason)
- Conditions: Ready=False, ContainersReady=False
- Resource requests vs node capacity issues

**Example Problematic Output:**
```
Events:
  Type     Reason     Age                  From               Message
  ----     ------     ----                 ----               -------
  Warning  BackOff    2m (x10 over 5m)     kubelet            Back-off restarting failed container
  Warning  Failed     1m (x8 over 5m)      kubelet            Error: container failed to start

Last State:     Terminated
  Reason:       Error
  Exit Code:    1
  Started:      Mon, 10 Nov 2025 10:15:23 +0000
  Finished:     Mon, 10 Nov 2025 10:15:25 +0000
```

### Get Current Container Logs
```bash
kubectl logs <pod-name> -n <namespace>
```

**Common Error Patterns:**
```
ModuleNotFoundError: No module named 'structlog'
ImportError: cannot import name 'X' from 'Y'
ConnectionRefusedError: [Errno 111] Connection refused
pymongo.errors.ServerSelectionTimeoutError: MongoDB connection timeout
```

### Get Logs from Previous (Crashed) Container
```bash
kubectl logs <pod-name> -n <namespace> --previous
```

**Use when:** Pod has restarted and current logs don't show the crash

### Get Events Filtered by Pod Name
```bash
kubectl get events -n <namespace> --field-selector involvedObject.name=<pod-name> --sort-by='.lastTimestamp'
```

### Analyze Resource Requests vs Node Capacity
```bash
kubectl describe node <node-name> | grep -A 10 "Allocated resources"
```

**Example Output:**
```
Allocated resources:
  Resource           Requests      Limits
  --------           --------      ------
  cpu                7550m (94%)   12000m (150%)
  memory             12Gi (75%)    24Gi (150%)
```

## Section 3: Cluster Resource Analysis

### Check CPU/Memory Usage Per Node
```bash
kubectl top nodes
```

**Example Output:**
```
NAME           CPU(cores)   CPU%   MEMORY(bytes)   MEMORY%
node-1         7550m        94%    12288Mi         75%
```

**Red Flag:** CPU > 90%, Memory > 85%

### Describe Nodes to See Allocated Resources and Capacity
```bash
kubectl describe nodes
```

**Look for:**
- Conditions: MemoryPressure=True, DiskPressure=True
- Allocatable vs Allocated resources
- Pods that couldn't be scheduled due to insufficient resources

### List Pods Sorted by Resource Consumption
```bash
# CPU usage
kubectl top pods -A --sort-by=cpu

# Memory usage
kubectl top pods -A --sort-by=memory
```

### Identify Resource Pressure Conditions
```bash
kubectl get nodes -o json | jq '.items[] | {name: .metadata.name, conditions: [.status.conditions[] | select(.status=="True") | .type]}'
```

**Healthy Output:**
```json
{
  "name": "node-1",
  "conditions": ["Ready"]
}
```

**Problematic Output:**
```json
{
  "name": "node-1",
  "conditions": ["Ready", "MemoryPressure", "DiskPressure"]
}
```

## Section 4: Dependency Health Check

### Verify MongoDB Pods are Running and Ready
```bash
kubectl get pods -n neural-hive-specialists -l app=mongodb -o wide
```

**Expected:** All MongoDB pods in Running state with 1/1 Ready

### Verify MLflow Pods are Running and Ready
```bash
kubectl get pods -n neural-hive-specialists -l app=mlflow -o wide
```

### Verify Neo4j Pods are Running and Ready
```bash
kubectl get pods -n neural-hive-specialists -l app=neo4j -o wide
```

### Verify Redis Pods are Running and Ready
```bash
kubectl get pods -n neural-hive-specialists -l app=redis -o wide
```

### Test Connectivity from Specialist Namespace to Each Dependency

#### Test MongoDB Connectivity
```bash
kubectl run -it --rm debug --image=mongo:5.0 --restart=Never -n neural-hive-specialists -- \
  mongosh "mongodb://mongodb.neural-hive-specialists.svc.cluster.local:27017" --eval "db.adminCommand('ping')"
```

**Expected Output:** `{ ok: 1 }`

#### Test MLflow Connectivity
```bash
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n neural-hive-specialists -- \
  curl -s http://mlflow.neural-hive-specialists.svc.cluster.local:5000/health
```

**Expected Output:** `200 OK` or health status JSON

#### Test Neo4j Connectivity
```bash
kubectl run -it --rm debug --image=neo4j:4.4 --restart=Never -n neural-hive-specialists -- \
  cypher-shell -a bolt://neo4j.neural-hive-specialists.svc.cluster.local:7687 -u neo4j -p password "RETURN 1"
```

**Expected Output:** `1`

#### Test Redis Connectivity
```bash
kubectl run -it --rm debug --image=redis:7-alpine --restart=Never -n neural-hive-specialists -- \
  redis-cli -h redis.neural-hive-specialists.svc.cluster.local -p 6379 PING
```

**Expected Output:** `PONG`

## Section 5: Image Availability Check

### List Current Image Tags Used by Specialist Deployments
```bash
kubectl get deployments -n neural-hive-specialists -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].image}{"\n"}{end}'
```

**Example Output:**
```
specialist-business         localhost:5000/specialist-business:v1.0.9
specialist-technical        localhost:5000/specialist-technical:v1.0.9
specialist-behavior         localhost:5000/specialist-behavior:v1.0.9
specialist-evolution        localhost:5000/specialist-evolution:v1.0.9
specialist-architecture     localhost:5000/specialist-architecture:v1.0.9
```

### Verify Images Exist in Local Registry
```bash
curl -s http://localhost:5000/v2/_catalog | jq
curl -s http://localhost:5000/v2/specialist-business/tags/list | jq
```

### Check Image Pull Policy Settings
```bash
kubectl get deployments -n neural-hive-specialists -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].imagePullPolicy}{"\n"}{end}'
```

**Recommended:** `IfNotPresent` for local registry

### Identify ImagePullBackOff Errors
```bash
kubectl get events -n neural-hive-specialists --field-selector reason=Failed,reason=BackOff | grep -i "image"
```

## Section 6: Configuration Validation

### Verify ConfigMaps Exist and Contain Required Keys
```bash
kubectl get configmaps -n neural-hive-specialists
kubectl describe configmap specialist-business-config -n neural-hive-specialists
```

**Check for required keys:**
- MONGODB_URI
- MLFLOW_TRACKING_URI
- NEO4J_URI
- REDIS_HOST
- KAFKA_BOOTSTRAP_SERVERS

### Verify Secrets Exist and Contain Required Keys
```bash
kubectl get secrets -n neural-hive-specialists
kubectl describe secret specialist-business-secret -n neural-hive-specialists
```

**Check for required keys:**
- MONGODB_PASSWORD
- NEO4J_PASSWORD
- REDIS_PASSWORD
- API_KEY

### Check Environment Variable Mappings in Deployments
```bash
kubectl get deployment specialist-business -n neural-hive-specialists -o jsonpath='{.spec.template.spec.containers[0].env[*]}' | jq
```

### Validate MongoDB URI Format Includes Authentication
```bash
kubectl get configmap specialist-business-config -n neural-hive-specialists -o jsonpath='{.data.MONGODB_URI}'
```

**Expected Format:** `mongodb://username:password@mongodb.neural-hive-specialists.svc.cluster.local:27017/database?authSource=admin`

## Quick Reference: Common Issues and Commands

| Issue | Quick Check Command |
|-------|---------------------|
| Pod crashes | `kubectl logs <pod> -n <ns> --previous` |
| Resource shortage | `kubectl top nodes` |
| Dependency down | `kubectl get pods -n <ns> -l app=<dependency>` |
| Image not found | `curl http://localhost:5000/v2/<image>/tags/list` |
| Config missing | `kubectl describe configmap <name> -n <ns>` |
| Network issue | `kubectl run -it --rm debug --image=curlimages/curl -- curl <url>` |

## Next Steps

After collecting diagnostics:

1. **Categorize failures** by root cause (image, resources, config, dependencies, health checks)
2. **Prioritize fixes** based on impact and ease of resolution
3. **Follow remediation guide** (REMEDIATION_GUIDE_PODS.md) for detailed fix procedures
4. **Validate fixes** using validation scripts after remediation

## Automated Diagnostic Collection

For automated diagnostic collection, use:
```bash
./scripts/diagnostics/collect-pod-diagnostics.sh
```

This script will automatically run all checks above and generate a comprehensive diagnostic report.
