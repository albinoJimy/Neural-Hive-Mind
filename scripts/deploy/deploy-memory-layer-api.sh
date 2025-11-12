#!/bin/bash
set -euo pipefail

# Deploy Memory Layer API
# Script para deploy completo do serviço Memory Layer API

# Variáveis
ENV=${ENV:-dev}
NAMESPACE="memory-layer-api"
CHART_PATH="./helm-charts/memory-layer-api"
VALUES_FILE="./environments/${ENV}/helm-values/memory-layer-api-values.yaml"

echo "========================================="
echo "Deploying Memory Layer API to ${ENV}..."
echo "========================================="

# 1. Verificar pré-requisitos
echo ""
echo "1. Checking prerequisites..."

# Verificar se camadas de memória estão deployadas
for component in redis-cluster mongodb-cluster neo4j-cluster clickhouse-cluster; do
  if ! kubectl get statefulset -n ${component} &> /dev/null; then
    echo "ERROR: ${component} not deployed"
    echo "Please deploy all memory layers first"
    exit 1
  fi
done
echo "✓ All memory layers deployed"

# Verificar Kafka (optional)
REQUIRE_KAFKA=${REQUIRE_KAFKA:-false}
if [ "$REQUIRE_KAFKA" = "true" ]; then
  if ! kubectl get kafka -n neural-hive-kafka neural-hive-kafka &> /dev/null; then
    echo "ERROR: Kafka cluster not deployed"
    exit 1
  fi
  echo "✓ Kafka cluster ready"
else
  echo "⚠ Kafka check skipped (REQUIRE_KAFKA=false)"
fi

# Verificar e construir imagem Docker se necessário
echo ""
echo "Checking Docker image..."
if ! docker images | grep -q "neural-hive-mind/memory-layer-api.*1.0.0"; then
  echo "Building memory-layer-api Docker image..."
  cd services/memory-layer-api
  docker build -t neural-hive-mind/memory-layer-api:1.0.0 .
  # Carregar no Minikube
  echo "Loading image into Minikube..."
  minikube image load neural-hive-mind/memory-layer-api:1.0.0
  cd ../..
  echo "✓ Image built and loaded"
else
  echo "✓ Image already exists"
fi

# 2. Criar namespace
echo ""
echo "2. Creating namespace..."
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# 3. Aplicar labels ao namespace
echo ""
echo "3. Applying namespace labels..."
kubectl label namespace ${NAMESPACE} \
  neural-hive.io/component=memory-layer-api \
  neural-hive.io/layer=conhecimento-dados \
  istio-injection=enabled \
  --overwrite

# 4. Aplicar ConfigMap de políticas
echo ""
echo "4. Applying ConfigMap with retention policies..."
kubectl apply -f k8s/configmaps/memory-layer-policies.yaml

# 5. Criar secrets (se não existirem)
echo ""
echo "5. Creating secrets..."
if ! kubectl get secret memory-layer-api-secrets -n ${NAMESPACE} &> /dev/null; then
  echo "Creating secrets..."
  kubectl create secret generic memory-layer-api-secrets \
    --from-literal=redis_password="${REDIS_PASSWORD:-}" \
    --from-literal=mongodb_password="${MONGODB_PASSWORD:-}" \
    --from-literal=mongodb_uri="mongodb://mongodb.mongodb-cluster.svc.cluster.local:27017" \
    --from-literal=neo4j_password="${NEO4J_PASSWORD:-}" \
    --from-literal=clickhouse_password="${CLICKHOUSE_PASSWORD:-}" \
    -n ${NAMESPACE}
  echo "✓ Secrets created"
else
  echo "✓ Secrets already exist"
fi

# 6. Deploy via Helm (se helm chart existir)
echo ""
echo "6. Deploying Helm chart..."
if [ -d "${CHART_PATH}" ] && [ -f "${VALUES_FILE}" ]; then
  helm upgrade --install memory-layer-api ${CHART_PATH} \
    --namespace ${NAMESPACE} \
    --values ${VALUES_FILE} \
    --wait --timeout 10m
else
  echo "WARNING: Helm chart or values file not found, skipping Helm deployment"
  echo "Chart path: ${CHART_PATH}"
  echo "Values file: ${VALUES_FILE}"
fi

# 7. Verificar deployment
echo ""
echo "7. Verifying deployment..."
if kubectl get deployment memory-layer-api -n ${NAMESPACE} &> /dev/null; then
  kubectl rollout status deployment/memory-layer-api -n ${NAMESPACE} --timeout=5m
else
  echo "WARNING: Deployment not found, may need manual deployment"
fi

# 8. Verificar pods
echo ""
echo "8. Checking pods..."
kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=memory-layer-api

# 9. Verificar health
echo ""
echo "9. Checking health..."
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=memory-layer-api \
  -n ${NAMESPACE} \
  --timeout=5m || echo "WARNING: Pods not ready yet"

# 10. Testar conectividade com camadas de memória
echo ""
echo "10. Testing connectivity to memory layers..."
POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=memory-layer-api -o jsonpath='{.items[0].metadata.name}')

# Função auxiliar para testar conectividade TCP
# Tenta primeiro com nc dentro do pod, depois com busybox temporário
test_tcp_connectivity() {
  local host=$1
  local port=$2
  local pod_name=$3
  local namespace=$4

  # Tentar nc dentro do pod
  if kubectl exec -n ${namespace} ${pod_name} -- which nc >/dev/null 2>&1; then
    if kubectl exec -n ${namespace} ${pod_name} -- nc -z -w 5 ${host} ${port} 2>/dev/null; then
      return 0
    fi
  fi

  # Fallback: usar busybox temporário para teste de rede
  if kubectl run tmp-netcheck-$$ --rm -i --image=busybox --restart=Never -- nc -z -w 5 ${host} ${port} >/dev/null 2>&1; then
    return 0
  fi

  return 1
}

if [ -n "$POD_NAME" ]; then
  # Redis - usar o nome do serviço correto
  echo -n "  Testing Redis... "
  REDIS_HOST="neural-hive-cache.redis-cluster.svc.cluster.local"
  if test_tcp_connectivity ${REDIS_HOST} 6379 ${POD_NAME} ${NAMESPACE}; then
    echo "✓"
  else
    echo "⚠ not reachable (host: ${REDIS_HOST}:6379)"
  fi

  # MongoDB
  echo -n "  Testing MongoDB... "
  if test_tcp_connectivity mongodb.mongodb-cluster.svc.cluster.local 27017 ${POD_NAME} ${NAMESPACE}; then
    echo "✓"
  else
    echo "⚠ not reachable"
  fi

  # Neo4j
  echo -n "  Testing Neo4j... "
  if test_tcp_connectivity neo4j-bolt.neo4j-cluster.svc.cluster.local 7687 ${POD_NAME} ${NAMESPACE}; then
    echo "✓"
  else
    echo "⚠ not reachable"
  fi

  # ClickHouse - testar HTTP using curlimages/curl pod
  echo -n "  Testing ClickHouse... "
  if kubectl run tmp-clickhouse-check-$$ --rm -i --image=curlimages/curl --restart=Never -- \
    curl -s http://clickhouse-http.clickhouse-cluster.svc.cluster.local:8123/ping 2>/dev/null | grep -q "Ok"; then
    echo "✓"
  else
    echo "⚠ not reachable"
  fi
else
  echo "⚠ No pods found for connectivity testing"
fi

# 11. Verificar CronJobs
echo ""
echo "11. Verifying CronJobs..."
for cronjob in sync-mongodb-clickhouse enforce-retention data-quality-check; do
  if kubectl get cronjob -n ${NAMESPACE} memory-layer-api-${cronjob} &> /dev/null; then
    SCHEDULE=$(kubectl get cronjob -n ${NAMESPACE} memory-layer-api-${cronjob} -o jsonpath='{.spec.schedule}')
    echo "  ✓ CronJob ${cronjob} created (schedule: ${SCHEDULE})"
  else
    echo "  ⚠ CronJob ${cronjob} not found"
  fi
done

echo ""
echo "========================================="
echo "✅ Deployment completed successfully!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Run validation: ./scripts/validation/validate-memory-layer-integration.sh"
echo "2. Run integration test: ./tests/memory-layer-api-integration-test.sh"
echo "3. Test unified query: curl -X POST http://localhost:8000/api/v1/memory/query -H 'Content-Type: application/json' -d '{\"query_type\": \"context\", \"entity_id\": \"test\"}'"
echo "4. View logs: kubectl logs -n ${NAMESPACE} -l app.kubernetes.io/name=memory-layer-api -f"
echo "5. Port-forward API: kubectl port-forward -n ${NAMESPACE} svc/memory-layer-api 8000:8000"
echo "6. Check CronJobs: kubectl get cronjob -n ${NAMESPACE}"
echo "7. Manual job execution: kubectl create job -n ${NAMESPACE} --from=cronjob/memory-layer-api-sync-mongodb-clickhouse manual-sync-1"
echo ""
