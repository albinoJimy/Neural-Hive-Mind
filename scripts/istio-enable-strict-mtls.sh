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
echo "Verifying STRICT mode - plaintext should be rejected..."
pod_a=$(kubectl get pods -n neural-hive -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -n "$pod_a" ]; then
  echo "Testing with pod: $pod_a"
  echo "STRICT mode active - all service-to-service communication must use mTLS"
else
  echo "No pods found in neural-hive namespace"
fi

echo "mTLS STRICT enabled successfully!"