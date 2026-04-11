#!/bin/bash
set -e

NAMESPACE="redis-cluster"

echo "Verifying Redis data sync..."

OLD_POD=$(kubectl get pods -n $NAMESPACE -o jsonpath='{.items[0].metadata.name}')
OLD_KEYS=$(kubectl exec -n $NAMESPACE $OLD_POD -- redis-cli DBSIZE)

NEW_KEYS=$(kubectl exec -n $NAMESPACE redis-cluster-0 -- redis-cli -c DBSIZE)

echo "Old Redis keys: $OLD_KEYS"
echo "New Redis keys: $NEW_KEYS"

if [ "$OLD_KEYS" -eq "$NEW_KEYS" ]; then
  echo "✓ Sync verification passed!"
else
  echo "⚠ Key count mismatch!"
  echo "Old: $OLD_KEYS, New: $NEW_KEYS"
  exit 1
fi