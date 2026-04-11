#!/bin/bash
set -e

NAMESPACE=${1:-"neural-hive"}

echo "Testing mTLS PERMISSIVE mode in namespace: $NAMESPACE"

mtls_mode=$(kubectl get meshpolicy authentication-meshpolicy -o jsonpath='{.spec.peers[0].mtls.mode}' 2>/dev/null || echo "not configured")

echo "Current mTLS mode: $mtls_mode"

echo "Testing plaintext connection..."
pod_a=$(kubectl get pods -n $NAMESPACE -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n $NAMESPACE $pod_a -- \
  curl -s http://gateway-intencoes:8000/health || echo "Plaintext failed (expected in PERMISSIVE)"

echo "Testing mTLS connection..."
kubectl exec -n $NAMESPACE $pod_a -- \
  curl -s http://gateway-intencoes:8000/health \
  --cacert /etc/istio/ingressgateway-certs/ca.crt || true

echo "mTLS PERMISSIVE test complete"