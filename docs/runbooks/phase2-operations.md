# Phase 2 Operations Runbook

## Overview
Phase 2 introduces 13 services across orchestration, strategic planning, optimization, observability, and governance. Critical dependencies include Temporal + PostgreSQL, MongoDB clusters, Kafka, Redis, Neo4j, ClickHouse, and Vault/SPIFFE for identity.

## Service Inventory
- Orchestrator Dynamic (namespace: neural-hive-orchestration, health: `/health`, gRPC 50051)
- Queen Agent (namespace: neural-hive-estrategica, health: `/health`, gRPC 50053)
- Worker Agents (namespace: neural-hive-execution, health: `/health`, gRPC 50052)
- Analyst Agents (namespace: neural-hive-analytics, health: `/health`, gRPC 50051)
- Optimizer Agents (namespace: neural-hive-estrategica, health: `/health`, gRPC 50051)
- Service Registry (namespace: neural-hive-registry, health: `/health`, gRPC 50051)
- Execution Ticket Service (namespace: neural-hive-orchestration, health: `/health`, gRPC 50052)
- Code Forge, SLA Management System, Self-Healing Engine, Guard/Scout Agents, MCP Tool Catalog

## Common Operations
- Start/Stop: `kubectl rollout restart deployment/<svc> -n <ns>`; pause with `kubectl scale deployment/<svc> --replicas=0`.
- Scale: `kubectl scale deployment/<svc> --replicas=R -n <ns>` or tune HPA via Helm values (`autoscaling.*`).
- Logs: `kubectl logs -n <ns> -l app.kubernetes.io/name=<svc> --tail=200 -f`.
- Metrics: Prometheus at `prometheus-server.monitoring:9090`; Grafana dashboard `phase2-resources`.
- Dashboards: CPU/Memory/HPA in `observability/grafana/dashboards/phase2-resources.json`.

## Troubleshooting by Service
### Orchestrator Dynamic
- **Temporal Workflow Stuck** (running >4h):  
  1. `kubectl exec -it orchestrator-dynamic-0 -n neural-hive-orchestration -- temporal workflow describe --workflow-id <id>`  
  2. Check worker logs: `kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=100 | grep <id>`  
  3. Restart worker if idle: `kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration`.  
  4. Cancel/retry: `temporal workflow cancel --workflow-id <id>`.  
  5. Inspect MongoDB `validation_audit` for root cause.
- **Service Registry Latency**: circuit breaker trips in scheduler; fallback uses cached workers. Inspect `circuit_breaker_state` and registry pods.

### Queen Agent
- **Strategic Decision Conflicts**: check MongoDB `strategic_decisions_ledger` and Neo4j reachability. Circuit breaker protects Neo4j; when open, retry after 30s.
- **Exception Approval Backlog**: inspect Kafka consumers on `plans.consensus` and MongoDB write capacity (pool gauges).

### Worker Agents
- **Execution Failures >10%**: validate downstream Code Forge and Vault tokens. Restart pods if `worker_agent_execution_failures_total` spikes.

### Analyst Agents
- **ClickHouse Timeouts**: verify pool sizes and network; check Redis cache hit rate. MongoDB pool gauges should stay below requested max.

### Optimizer Agents
- **RL Training Failures**: confirm MLflow availability and MongoDB connections; PgBouncer host for Temporal should be reachable from orchestrator.

### Service Registry
- **Agent Registration Fails**: validate etcd quorum and certificate validity; check circuit breaker in scheduler logs.

### Code Forge
- **Pipeline Failures**: review `code_forge_pipelines_failed_total` alerts, Git credentials, and OPA policy responses.

### SLA Management System
- **Budget Exhaustion**: inspect budgets in Redis; adjust calculator thresholds; verify Alertmanager webhooks.

### Execution Ticket Service
- **Connection Pool Exhaustion**: monitor Postgres via pgBouncer and MongoDB pools. Scale to reduce queue depth; check webhooks latency.

## Alert Response Procedures
- Reference `monitoring/alerts/phase2-critical-alerts.yaml` and `monitoring/alerts/circuit-breaker-alerts.yaml`.
- Circuit breaker open >2m: check downstream dependency health, reduce traffic (`kubectl scale`), and verify retry storms.
- PostgreSQL backup failure: rerun CronJob, verify S3 access, and consult recovery script (`scripts/maintenance/restore-postgres-temporal.sh`).

## Disaster Recovery (Summary)
- PostgreSQL Temporal: restore from S3 backup, replay WAL, scale Temporal frontend back to 3 replicas.
- MongoDB: restore DR snapshot, rebuild replica set, reindex collections, validate hashes.
- Kafka: replay from MirrorMaker backup and restore consumer offsets.

## Escalation Paths
- L1: On-call SRE (triage + rollback)
- L2: Service owners (Orchestrator/Queen/Registry)
- L3: Engineering Manager and Database Reliability
