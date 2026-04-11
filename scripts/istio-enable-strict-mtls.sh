#!/bin/bash
set -e

echo "Enabling mTLS STRICT mode..."

kubectl apply -f helm/istio-base/mtls-strict.yaml

sleep 10

echo "Verifying mTLS STRICT mode..."
for ns in istio-system neural-hive kafka redis-cluster; do
  mode=$(kubectl get peerauthentication -n $ns -o jsonpath='{.items[0].spec.mtls.mode}' 2>/dev/null || echo "N/A")
  echo "Namespace $ns: $mode"
done

echo "Testing service-to-service communication..."
./scripts/istio-test-mtls.sh neural-hive

echo "mTLS STRICT enabled successfully!"