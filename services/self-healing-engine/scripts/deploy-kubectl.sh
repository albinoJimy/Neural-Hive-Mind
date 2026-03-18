#!/bin/bash
# Script de deploy do Self-Healing Engine via kubectl

set -e

NAMESPACE="neural-hive-orchestration"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$SCRIPT_DIR/kubernetes"

echo "🚀 Deploying Self-Healing Engine..."
echo "Namespace: $NAMESPACE"

# Criar namespace se não existir
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Aplicar manifests em ordem
echo "📦 Applying Kubernetes manifests..."

# Service Account e RBAC
kubectl apply -f "$K8S_DIR/serviceaccount.yaml"

# ConfigMap com playbooks
kubectl apply -f "$K8S_DIR/configmap.yaml"

# Secret (placeholder - atualizar com valores reais em prod)
kubectl apply -f "$K8S_DIR/secret.yaml"

# Deployment
kubectl apply -f "$K8S_DIR/deployment.yaml"

# Service
kubectl apply -f "$K8S_DIR/service.yaml"

# HPA
kubectl apply -f "$K8S_DIR/hpa.yaml"

# PDB
kubectl apply -f "$K8S_DIR/pdb.yaml"

# NetworkPolicy
kubectl apply -f "$K8S_DIR/networkpolicy.yaml"

echo "⏳ Waiting for deployment to be ready..."
kubectl rollout status deployment/self-healing-engine -n "$NAMESPACE" --timeout=5m

echo "✅ Self-Healing Engine deployed successfully!"
echo ""
echo "🔍 Check pods:"
kubectl get pods -n "$NAMESPACE" -l app=self-healing-engine
echo ""
echo "📊 Check logs:"
kubectl logs -f deployment/self-healing-engine -n "$NAMESPACE" --tail=50
