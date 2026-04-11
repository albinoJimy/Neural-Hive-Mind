#!/bin/bash
set -e

echo "Enabling Gatekeeper enforcement mode..."

echo "Current violations:"
kubectl get violations -A 2>/dev/null || echo "No violations"

echo ""
read -p "Continue with enforcement activation? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Aborted"
  exit 1
fi

helm upgrade gatekeeper helm/gatekeeper \
  --namespace gatekeeper-system \
  --values helm/gatekeeper/enforcement-values.yaml \
  --wait

echo "Waiting for Gatekeeper to restart..."
sleep 30

kubectl get validatingwebhookconfiguration | grep gatekeeper

kubectl get pods -n gatekeeper-system

echo ""
echo "Enforcement mode enabled!"
echo "Testing constraint enforcement..."