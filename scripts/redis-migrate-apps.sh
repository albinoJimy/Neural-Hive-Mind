#!/bin/bash
set -e

APP_NAMESPACE=${1:-"neural-hive"}

echo "Migrating applications in $APP_NAMESPACE to new Redis Cluster..."

deployments=$(kubectl get deployments -n $APP_NAMESPACE -o jsonpath='{.items[*].metadata.name}')

for deployment in $deployments; do
  echo "Updating deployment: $deployment"

  kubectl set env deployment/$deployment \
    REDIS_HOST=redis-cluster.redis-cluster.svc.cluster.local \
    REDIS_PORT=6379 \
    REDIS_TLS_ENABLED=true \
    REDIS_CLUSTER_MODE=true \
    -n $APP_NAMESPACE \
    --dry-run=client -o yaml | kubectl apply -f -

  kubectl patch deployment $deployment -n $APP_NAMESPACE --patch='
  {
    "spec": {
      "template": {
        "spec": {
          "volumes": [{
            "name": "redis-client-tls",
            "secret": {
              "secretName": "redis-client-tls",
              "optional": true
            }
          }],
          "containers": [{
            "name": "*",
            "volumeMounts": [{
              "name": "redis-client-tls",
              "mountPath": "/etc/redis/tls",
              "readOnly": true
            }],
            "env": [{
              "name": "REDIS_TLS_CA",
              "value": "/etc/redis/tls/ca.crt"
            }, {
              "name": "REDIS_TLS_CERT",
              "value": "/etc/redis/tls/tls.crt"
            }, {
              "name": "REDIS_TLS_KEY",
              "value": "/etc/redis/tls/tls.key"
            }]
          }]
        }
      }
    }
  }'

  kubectl rollout restart deployment/$deployment -n $APP_NAMESPACE
  kubectl rollout status deployment/$deployment -n $APP_NAMESPACE --timeout=300s

  echo "Deployment $deployment updated and restarted"
done

echo "Application migration complete!"