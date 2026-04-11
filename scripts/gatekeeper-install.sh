#!/bin/bash
set -e

NAMESPACE="gatekeeper-system"
ENV=${1:-dev}

echo "Installing OPA Gatekeeper in $ENV environment..."

kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts
helm repo update

helm dependency build helm/gatekeeper

helm upgrade --install gatekeeper helm/gatekeeper \
  --namespace $NAMESPACE \
  --values helm/gatekeeper/values.yaml \
  --create-namespace \
  --wait \
  --timeout 10m

echo "Waiting for Gatekeeper to be ready..."
kubectl wait --for=condition=ready --timeout=300s \
  pod -l control-plane=controller-manager -n $NAMESPACE

echo "Gatekeeper installed successfully!"
echo "Current mode: AUDIT (not blocking)"