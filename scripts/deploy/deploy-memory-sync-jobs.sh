#!/bin/bash
set -euo pipefail

# Deploy Memory Sync Jobs
# Script para deploy dos CronJobs de sincronização e qualidade de dados

ENV=${ENV:-dev}

echo "========================================="
echo "Deploying Memory Sync Jobs to ${ENV}..."
echo "========================================="

# 1. Verificar pré-requisitos
echo ""
echo "1. Checking prerequisites..."

# Verificar se Memory Layer API está deployado
if ! kubectl get deployment -n memory-layer-api memory-layer-api &> /dev/null; then
  echo "ERROR: Memory Layer API not deployed"
  echo "Please run ./scripts/deploy/deploy-memory-layer-api.sh first"
  exit 1
fi
echo "✓ Memory Layer API deployed"

# 2. Criar ServiceAccount para jobs
echo ""
echo "2. Creating ServiceAccount and RBAC..."
kubectl apply -f - <<EOF
apiVersion: v1
kind: ServiceAccount
metadata:
  name: memory-sync-sa
  namespace: memory-layer-api
  labels:
    neural-hive.io/component: memory-sync
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: memory-sync-role
  namespace: memory-layer-api
rules:
- apiGroups: [""]
  resources: ["configmaps", "secrets"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: memory-sync-rolebinding
  namespace: memory-layer-api
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: memory-sync-role
subjects:
- kind: ServiceAccount
  name: memory-sync-sa
  namespace: memory-layer-api
EOF
echo "✓ ServiceAccount and RBAC created"

# 3. Deploy CronJobs
echo ""
echo "3. Deploying CronJobs..."

echo "  - MongoDB → ClickHouse sync..."
kubectl apply -f k8s/jobs/memory-sync-mongodb-to-clickhouse.yaml

echo "  - Retention cleanup..."
kubectl apply -f k8s/jobs/memory-cleanup-retention.yaml

echo "  - Data quality check..."
kubectl apply -f k8s/jobs/data-quality-check.yaml

# 4. Verificar CronJobs
echo ""
echo "4. Verifying CronJobs..."
kubectl get cronjobs -n memory-layer-api

echo ""
echo "========================================="
echo "✅ CronJobs deployed successfully!"
echo "========================================="
echo ""
echo "Schedules:"
echo "  - MongoDB → ClickHouse sync: daily at 2 AM UTC"
echo "  - Retention cleanup: daily at 3 AM UTC"
echo "  - Data quality check: every 6 hours"
echo ""
echo "Commands:"
echo "  - List jobs: kubectl get cronjobs -n memory-layer-api"
echo "  - Trigger manual run: kubectl create job --from=cronjob/<name> <job-name> -n memory-layer-api"
echo "  - View logs: kubectl logs -n memory-layer-api job/<job-name>"
