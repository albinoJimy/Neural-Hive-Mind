# MongoDB and MLflow Infrastructure Validation Guide

## Overview
This guide provides step-by-step validation procedures for MongoDB authentication and MLflow connectivity after applying infrastructure fixes.

## Prerequisites
- Kubernetes cluster access with kubectl configured
- All specialist services deployed with updated configurations
- MongoDB and MLflow services running

## Phase 1: MongoDB Authentication Validation

### 1.1 Verify MongoDB Secret Configuration
```bash
# Check specialist-business secret
kubectl get secret specialist-business-secret -n neural-hive-specialists -o jsonpath='{.data.mongodb_uri}' | base64 -d

# Expected output should contain:
# mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive_dev?authSource=admin

# Repeat for all 5 specialists:
# specialist-technical, specialist-behavior, specialist-evolution, specialist-architecture
```

### 1.2 Test MongoDB Connectivity from Specialist Pods
```bash
# Get a specialist pod name
POD=$(kubectl get pods -n neural-hive-specialists -l app.kubernetes.io/name=specialist-business -o jsonpath='{.items[0].metadata.name}')

# Test MongoDB connection
kubectl exec -n neural-hive-specialists $POD -- python3 -c "
import os
from pymongo import MongoClient
uri = os.environ.get('MONGODB_URI')
print(f'Testing connection to: {uri}')
client = MongoClient(uri)
print('Databases:', client.list_database_names())
print('✅ MongoDB connection successful!')
"
```

### 1.3 Check Specialist Logs for MongoDB Errors
```bash
# Check for authentication errors
kubectl logs -n neural-hive-specialists -l app.kubernetes.io/name=specialist-business --tail=100 | grep -i "mongo\|auth"

# Should NOT see errors like:
# - "Authentication failed"
# - "not authorized"
# - "MongoServerError"
```

### 1.4 Verify Opinion Storage
```bash
# Connect to MongoDB and check collections
kubectl exec -n mongodb-cluster mongodb-0 -- mongosh \
  --username root \
  --password local_dev_password \
  --authenticationDatabase admin \
  --eval "use neural_hive_dev; db.specialist_opinions.countDocuments({})"

# Should return count without errors
```

## Phase 2: MLflow Validation

### 2.1 Verify MLflow Pod Status
```bash
# Check MLflow pod is running
kubectl get pods -n mlflow

# Check for permission errors in logs
kubectl logs -n mlflow -l app=mlflow --tail=100 | grep -i "permission\|error"

# Should NOT see:
# - "Permission denied"
# - "cannot write to directory"
```

### 2.2 Test MLflow API Connectivity
```bash
# Port-forward MLflow service
kubectl port-forward -n mlflow svc/mlflow 5000:5000 &

# Test health endpoint
curl http://localhost:5000/health

# Expected: {"status": "ok"}

# List experiments
curl http://localhost:5000/api/2.0/mlflow/experiments/list
```

### 2.3 Verify Specialist MLflow Connectivity
```bash
# Get specialist pod
POD=$(kubectl get pods -n neural-hive-specialists -l app.kubernetes.io/name=specialist-business -o jsonpath='{.items[0].metadata.name}')

# Test MLflow connection from specialist
kubectl exec -n neural-hive-specialists $POD -- python3 -c "
import os
import mlflow
mlflow.set_tracking_uri(os.environ.get('MLFLOW_TRACKING_URI'))
print('MLflow URI:', mlflow.get_tracking_uri())
experiments = mlflow.search_experiments()
print(f'✅ Found {len(experiments)} experiments')
"
```

### 2.4 Check MLflow Volume Permissions
```bash
# Check volume mount permissions
kubectl exec -n mlflow -l app=mlflow -- ls -la /mlflow

# Expected output should show:
# - Owner: 1000:1000 (if using non-root securityContext)
# - Writable by the container user
# - No permission denied errors
```

### 2.5 Verify MLflow Environment Variables

```bash
# Check all MLflow env vars are injected
for specialist in business technical behavior evolution architecture; do
  echo "\n=== Checking specialist-$specialist ==="
  POD=$(kubectl get pods -n neural-hive-specialists -l app.kubernetes.io/name=specialist-$specialist -o jsonpath='{.items[0].metadata.name}')

  kubectl exec -n neural-hive-specialists $POD -- env | grep MLFLOW

  # Expected output:
  # MLFLOW_TRACKING_URI=http://mlflow.mlflow.svc.cluster.local:5000
  # MLFLOW_EXPERIMENT_NAME=<specialist>-specialist
  # MLFLOW_MODEL_NAME=<specialist>-evaluator
  # MLFLOW_MODEL_STAGE=Production
done

# Verify volume mount exists
kubectl get pod -n neural-hive-specialists $POD -o jsonpath='{.spec.containers[0].volumeMounts}' | grep mlruns
```

## Phase 3: End-to-End Validation

### 3.1 Trigger Specialist Evaluation
```bash
# Send test request to specialist
kubectl exec -n neural-hive-specialists $POD -- curl -X POST http://localhost:8000/health

# Check logs for successful MongoDB write
kubectl logs -n neural-hive-specialists $POD --tail=50 | grep -i "opinion.*saved\|mongodb.*success"
```

### 3.2 Verify All 5 Specialists
```bash
# Run validation for each specialist
for specialist in business technical behavior evolution architecture; do
  echo "\n=== Validating specialist-$specialist ==="
  POD=$(kubectl get pods -n neural-hive-specialists -l app.kubernetes.io/name=specialist-$specialist -o jsonpath='{.items[0].metadata.name}')

  if [ -z "$POD" ]; then
    echo "❌ Pod not found for specialist-$specialist"
    continue
  fi

  # Check readiness
  kubectl get pod -n neural-hive-specialists $POD -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'

  # Check MongoDB env var
  kubectl exec -n neural-hive-specialists $POD -- env | grep MONGODB_URI | head -c 50
  echo "..."

  # Check MLflow env var
  kubectl exec -n neural-hive-specialists $POD -- env | grep MLFLOW_TRACKING_URI

  echo "✅ specialist-$specialist validated"
done
```

## Troubleshooting

### MongoDB Connection Issues

**Symptom**: "Authentication failed" errors
- Verify secret contains correct URI with credentials
- Check MongoDB pod is running: `kubectl get pods -n mongodb-cluster`
- Verify MongoDB user exists: `kubectl exec -n mongodb-cluster mongodb-0 -- mongosh --eval "db.getUsers()"`

**Symptom**: "authSource" errors
- Ensure URI includes `?authSource=admin` parameter
- Verify MongoDB authentication is enabled in mongodb-values.yaml

### MLflow Permission Issues

**Symptom**: "Permission denied" on /mlflow directory
- Verify securityContext is applied: `kubectl get deployment -n mlflow mlflow -o yaml | grep -A 5 securityContext`
- Check pod is running with correct user: `kubectl exec -n mlflow -l app=mlflow -- id`
- Restart MLflow pod to apply new securityContext

**Symptom**: Specialists can't reach MLflow
- Verify MLflow service exists: `kubectl get svc -n mlflow`
- Test DNS resolution: `kubectl exec -n neural-hive-specialists $POD -- nslookup mlflow.mlflow.svc.cluster.local`
- Check network policies allow traffic from specialists namespace

## Success Criteria

✅ All 5 specialist pods are in Ready state
✅ No MongoDB authentication errors in specialist logs
✅ Specialists can write opinions to MongoDB
✅ MLflow pod has no permission errors
✅ Specialists can connect to MLflow tracking server
✅ MLflow can list experiments without errors
✅ All specialists have MLFLOW_EXPERIMENT_NAME, MLFLOW_MODEL_NAME, MLFLOW_MODEL_STAGE env vars
✅ All specialists have /app/mlruns volume mount

## Rollback Procedure

If issues occur after deployment:

```bash
# Rollback specialist deployments
for specialist in business technical behavior evolution architecture; do
  helm rollback specialist-$specialist -n neural-hive-specialists
done

# Rollback MLflow deployment
kubectl rollout undo deployment/mlflow -n mlflow
```
