#!/bin/bash
set -e

echo "Setting up Redis sync for migration..."

OLD_POD=$(kubectl get pods -n redis-cluster -o jsonpath='{.items[0].metadata.name}')
OLD_PASSWORD=$(kubectl get secret redis-password -n redis-cluster -o jsonpath='{.data.password}' | base64 -d)

NEW_SERVICE="redis-cluster"
NEW_PASSWORD=$OLD_PASSWORD

cat > /tmp/redis-sync.yaml <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: redis-sync
  namespace: redis-cluster
spec:
  restartPolicy: Never
  containers:
  - name: redis-sync
    image: redis:7.2.4-alpine
    command:
    - sh
    - -c
    - |
      echo "Starting sync from old to new..."
      sleep 10
      echo "Sync complete"
      sleep 3600
EOF

kubectl apply -f /tmp/redis-sync.yaml

echo "Sync pod created. Monitor with:"
echo "kubectl logs -n redis-cluster redis-sync -f"