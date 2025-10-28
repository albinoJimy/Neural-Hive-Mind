#!/bin/bash
# Deploy Code Forge to Kubernetes

set -e

NAMESPACE="neural-hive-execution"
RELEASE_NAME="code-forge"
CHART_PATH="./helm-charts/code-forge"

echo "==> Deploying Code Forge"

# Validar pré-requisitos
echo "==> Validating prerequisites..."
command -v kubectl >/dev/null 2>&1 || { echo "kubectl not found"; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "helm not found"; exit 1; }

# Criar namespace se não existir
echo "==> Creating namespace if not exists..."
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# Deploy com Helm
echo "==> Deploying with Helm..."
helm upgrade --install ${RELEASE_NAME} ${CHART_PATH} \
  --namespace ${NAMESPACE} \
  --create-namespace \
  --wait \
  --timeout 5m

# Verificar deployment
echo "==> Verifying deployment..."
kubectl rollout status deployment/${RELEASE_NAME} -n ${NAMESPACE}

# Exibir pods
echo "==> Pods:"
kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=${RELEASE_NAME}

# Exibir service
echo "==> Service:"
kubectl get svc ${RELEASE_NAME} -n ${NAMESPACE}

echo "==> Code Forge deployed successfully!"
