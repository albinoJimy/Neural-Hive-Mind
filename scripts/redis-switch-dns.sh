#!/bin/bash
set -e

echo "Switching DNS to new Redis Cluster..."

cat > /tmp/redis-service.yaml <<EOF
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: redis-cluster
spec:
  type: ClusterIP
  clusterIP: None
  ports:
  - port: 6379
    targetPort: 6379
EOF

kubectl apply -f /tmp/redis-service.yaml

echo "DNS switch complete!"
echo "Applications can now use 'redis.redis-cluster.svc.cluster.local' or 'redis-cluster.redis-cluster.svc.cluster.local'"

kubectl run test-dns --image=busybox:1.36 --rm -it --restart=Never -n redis-cluster -- \
  nslookup redis.redis-cluster.svc.cluster.local || true