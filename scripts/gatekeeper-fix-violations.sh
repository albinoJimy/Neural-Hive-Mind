#!/bin/bash
set -e

NAMESPACE=${1:-"neural-hive"}

echo "Fixing common violations in namespace: $NAMESPACE"

# Add missing labels to deployments
echo "Adding required labels to deployments..."
deployments=$(kubectl get deployments -n $NAMESPACE -o jsonpath='{.items[*].metadata.name}')

for deployment in $deployments; do
  echo "Processing deployment: $deployment"

  current_labels=$(kubectl get deployment $deployment -n $NAMESPACE -o jsonpath='{.metadata.labels}')

  kubectl label deployment $deployment \
    app=$deployment \
    part-of=neural-hive-mind \
    managed-by=helm \
    --overwrite -n $NAMESPACE

  if ! echo "$current_labels" | grep -q "version"; then
    kubectl label deployment $deployment version=v1 -n $NAMESPACE --overwrite
  fi
done

# Add labels to services
echo "Adding required labels to services..."
services=$(kubectl get services -n $NAMESPACE -o jsonpath='{.items[*].metadata.name}')

for service in $services; do
  echo "Processing service: $service"
  kubectl label service $service \
    app=$service \
    component=service \
    part-of=neural-hive-mind \
    managed-by=helm \
    --overwrite -n $NAMESPACE
done

# Add labels to pods (via rollout restart)
echo "Restarting deployments to propagate labels to pods..."
for deployment in $deployments; do
  kubectl rollout restart deployment/$deployment -n $NAMESPACE
done

echo "Violation fix complete!"