#!/bin/bash
set -e

NAMESPACE="redis-cluster"
ENV=${1:-dev}

echo "Installing Redis Cluster in $ENV environment..."

kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

EXISTING_PASSWORD=$(kubectl get secret redis-password -n $NAMESPACE -o jsonpath='{.data.password}' 2>/dev/null || echo "")
if [ -z "$EXISTING_PASSWORD" ]; then
  EXISTING_PASSWORD=$(openssl rand -base64 32)
  kubectl create secret generic redis-password --from-literal=password=$EXISTING_PASSWORD -n $NAMESPACE
fi

helm dependency build helm/redis-cluster

helm upgrade --install redis-cluster helm/redis-cluster \
  --namespace $NAMESPACE \
  --values helm/redis-cluster/values.yaml \
  --set redis.auth.existingSecret=redis-password \
  --create-namespace \
  --wait \
  --timeout 15m

echo "Waiting for Redis Cluster to be ready..."
kubectl wait --for=condition=ready --timeout=600s \
  pod -l app.kubernetes.io/name=redis -n $NAMESPACE

echo "Redis Cluster installed successfully!"
kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=redis