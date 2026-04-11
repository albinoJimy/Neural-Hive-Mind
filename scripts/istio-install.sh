#!/bin/bash
set -e

# Verify required commands
for cmd in kubectl helm jq; do
  if ! command -v $cmd &> /dev/null; then
    echo "Error: $cmd is not installed"
    exit 1
  fi
done

NAMESPACE="istio-system"
ENV=${1:-dev}

# Validate environment parameter
if [[ ! "$ENV" =~ ^(dev|staging|prod)$ ]]; then
  echo "Error: ENV must be one of: dev, staging, prod"
  exit 1
fi

echo "Installing Istio in $ENV environment..."

kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

helm repo add istio https://istio-release.storage.googleapis.com/charts
helm repo update

helm dependency build helm/istio-base

helm upgrade --install istio-base helm/istio-base \
  --namespace $NAMESPACE \
  --values helm/istio-base/values.yaml \
  --create-namespace \
  --wait \
  --timeout 10m

echo "Waiting for istiod to be ready..."
kubectl wait --for=condition=available --timeout=300s \
  deployment/istiod -n $NAMESPACE

echo "Istio installed successfully!"