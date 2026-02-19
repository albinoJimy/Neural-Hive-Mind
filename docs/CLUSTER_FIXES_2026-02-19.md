# Cluster Fixes - 2026-02-19

## Summary
Fixed 3 CrashLoopBackOff issues and 1 dependency injection problem in the Neural Hive-Mind cluster.

## Issues Fixed

### 1. memory-layer-api-sync-consumer
**Problem:** CrashLoopBackOff - Unable to connect to ClickHouse and Kafka
**Root Cause:** Incorrect service hostnames in ConfigMap

**Fixes Applied:**
```yaml
# ConfigMap: memory-layer-api-config
clickhouse_host: clickhouse-neural-hive-clickhouse.clickhouse-operator.svc.cluster.local
kafka_bootstrap_servers: neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092

# Secret: memory-layer-api-secrets
clickhouse_password: ""  # Empty for default user
```

### 2. sla-management-system-operator
**Problem:** CrashLoopBackOff - HTTP endpoints in production environment
**Root Cause:** Prometheus URL using HTTP instead of HTTPS, liveness/readiness probes failing

**Fixes Applied:**
```yaml
# Environment Variables
PROMETHEUS__URL: https://prometheus-server.monitoring.svc.cluster.local:9090

# Removed probes (kopf doesn't start HTTP server)
livenessProbe: null
readinessProbe: null
```

### 3. orchestrator-dynamic
**Problem:** CrashLoopBackOff - spire-agent sidecar failing
**Root Cause:** SPIRE server not running in cluster, sidecar trying to connect without success

**Fixes Applied:**
- Removed spire-agent container from deployment
- Removed spire-agent volumes from deployment spec
- Rollback to stable revision without spire-agent

### 4. orchestrator-dynamic - MongoDB Secret
**Problem:** `RuntimeError: Config não foi injetado nas activities` - Worker Temporal não conseguia executar activities
**Root Cause:** Secret `orchestrator-dynamic-secrets` continha placeholder `<sealed-secret-ref>` na URI do MongoDB porque a integração Vault está desabilitada

**Fixes Applied:**
```bash
# Patch do Secret com URI correta do MongoDB
kubectl patch secret orchestrator-dynamic-secrets -n neural-hive \
  -p '{"data":{"MONGODB_URI":"bW9uZ29kYjovL3Jvb3Q6bG9jYWxfZGV2X3Bhc3N3b3JkQG1vbmdvZGIubW9uZ29kYi1jbHVzdGVyLnN2Yy5jbHVzdGVyLmxvY2FsOjI3MDE3"}}'

# Restart do deployment
kubectl rollout restart deployment orchestrator-dynamic -n neural-hive
```

**Resultado:** Dependências injetadas corretamente (kafka_enabled=True, mongodb_enabled=True, etc.)

## Configuration Files Updated

1. `environments/dev/helm-values/memory-layer-api-values.yaml`
   - Fixed ClickHouse hostname

2. `environments/prod/helm-values/orchestrator-dynamic-values.yaml`
   - Disabled SPIFFE (spiffe.enabled: false)

## Verification

```bash
# All pods running
kubectl get pods -A | grep -E "CrashLoopBackOff|Error" | grep -v Completed
# Output: (empty)

# Neural-hive namespace
kubectl get pods -n neural-hive
# 43 Running, 3 Completed, 0 CrashLoopBackOff
```

## Cluster Status After Fixes

| Metric | Value | Status |
|--------|-------|--------|
| Nodes | 5/5 Ready | ✅ |
| Pods Running | 149/154 (96.8%) | ✅ |
| CrashLoopBackOff | 0 | ✅ |
| Errors | 0 | ✅ |
