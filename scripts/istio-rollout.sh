#!/bin/bash
set -e

NAMESPACE=${1:-"neural-hive"}

echo "Rolling out Istio sidecar injection for namespace: $NAMESPACE"

kubectl label namespace $NAMESPACE \
  istio-injection=enabled \
  istio.io_rev=default \
  --overwrite

echo "Namespace labeled. Restarting deployments..."

deployments=$(kubectl get deployments -n $NAMESPACE -o jsonpath='{.items[*].metadata.name}')

for deployment in $deployments; do
  echo "Restarting deployment: $deployment"
  kubectl rollout restart deployment/$deployment -n $NAMESPACE
  kubectl rollout status deployment/$deployment -n $NAMESPACE --timeout=300s
done

echo "Rollout complete for namespace: $NAMESPACE"

pods_with_sidecar=$(kubectl get pods -n $NAMESPACE -o json | \
  jq -r '.items[] | select(.spec.containers[].name == "istio-proxy") | .metadata.name' | \
  wc -l)

total_pods=$(kubectl get pods -n $NAMESPACE --no-headers | wc -l)

echo "Pods with sidecar: $pods_with_sidecar / $total_pods"