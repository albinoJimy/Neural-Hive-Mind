#!/bin/bash
set -euo pipefail

# Variáveis
ENV=${ENV:-dev}
NAMESPACE="consensus-engine"
CHART_PATH="./helm-charts/consensus-engine"
VALUES_FILE="./environments/${ENV}/helm-values/consensus-engine-values.yaml"

echo "Deploying Consensus Engine to ${ENV}..."

# 1. Verificar pré-requisitos
echo "Checking prerequisites..."

# Verificar se especialistas estão deployados
for specialist in business technical behavior evolution architecture; do
  if ! kubectl get deployment -n specialist-${specialist} specialist-${specialist} &> /dev/null; then
    echo "ERROR: Specialist ${specialist} not deployed"
    exit 1
  fi
done
echo "✓ All specialists deployed"

# Verificar se MongoDB está disponível
if ! kubectl get statefulset -n mongodb-cluster &> /dev/null; then
  echo "ERROR: MongoDB not deployed"
  exit 1
fi
echo "✓ MongoDB available"

# Verificar se Redis está disponível
if ! kubectl get statefulset -n redis-cluster &> /dev/null; then
  echo "ERROR: Redis not deployed"
  exit 1
fi
echo "✓ Redis available"

# Verificar e construir imagem Docker se necessário
echo "Checking Docker image..."
if ! docker images | grep -q "neural-hive-mind/consensus-engine.*1.0.0"; then
  echo "Building consensus-engine Docker image..."
  cd services/consensus-engine
  docker build -t neural-hive-mind/consensus-engine:1.0.0 .
  # Carregar no Minikube
  echo "Loading image into Minikube..."
  minikube image load neural-hive-mind/consensus-engine:1.0.0
  cd ../..
  echo "✓ Image built and loaded"
else
  echo "✓ Image already exists"
fi

# 2. Criar namespace
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# 3. Aplicar labels
kubectl label namespace ${NAMESPACE} \
  neural-hive.io/component=consensus-aggregator \
  neural-hive.io/layer=cognitiva \
  istio-injection=enabled \
  --overwrite

# 4. Criar secrets (se não existirem)
if ! kubectl get secret consensus-engine-secrets -n ${NAMESPACE} &> /dev/null; then
  echo "Creating secrets..."
  kubectl create secret generic consensus-engine-secrets \
    --from-literal=kafka_sasl_password="${KAFKA_SASL_PASSWORD:-}" \
    --from-literal=mongodb_password="${MONGODB_PASSWORD:-}" \
    --from-literal=redis_password="${REDIS_PASSWORD:-}" \
    -n ${NAMESPACE}
fi

# 5. Deploy via Helm
echo "Deploying Helm chart..."
helm upgrade --install consensus-engine ${CHART_PATH} \
  --namespace ${NAMESPACE} \
  --values ${VALUES_FILE} \
  --wait --timeout 10m

# 6. Verificar deployment
echo "Verifying deployment..."
kubectl rollout status deployment/consensus-engine -n ${NAMESPACE}

# 7. Verificar pods
kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=consensus-engine

# 8. Verificar health
echo "Checking health..."
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=consensus-engine \
  -n ${NAMESPACE} \
  --timeout=5m

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

# 9. Testar conectividade gRPC com especialistas
echo ""
echo "Testing gRPC connectivity to specialists..."
POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[0].metadata.name}')
for specialist in business technical behavior evolution architecture; do
  SPECIALIST_HOST="specialist-${specialist}.specialist-${specialist}.svc.cluster.local"
  if test_tcp_connectivity ${SPECIALIST_HOST} 50051 ${POD_NAME} ${NAMESPACE}; then
    echo "✓ ${specialist} specialist reachable"
  else
    echo "⚠ ${specialist} specialist not reachable (may need time to start)"
  fi
done

# 10. Testar conectividade com Kafka (producer real)
echo ""
echo "Testing Kafka connectivity..."
# Primeiro, verificar logs para conexão básica
if kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=50 2>/dev/null | grep -qi "kafka.*connected\|consumer.*started"; then
  echo "✓ Kafka consumer connection confirmed"
else
  echo "⚠ Kafka consumer connection not yet confirmed (check logs)"
fi

# Testar producer real enviando mensagem de teste
echo "Testing Kafka producer..."
KAFKA_POD=$(kubectl get pods -n neural-hive-kafka -l app.kubernetes.io/name=kafka -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$KAFKA_POD" ]; then
  KAFKA_BOOTSTRAP="neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local:9092"
  if kubectl exec -n neural-hive-kafka ${KAFKA_POD} -- timeout 10 kafka-console-producer \
    --bootstrap-server ${KAFKA_BOOTSTRAP} \
    --topic plans.ready 2>/dev/null <<< '{"test":true,"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}'; then
    echo "✓ Kafka producer test successful (message sent to plans.ready)"
  else
    echo "⚠ Kafka producer test failed (may need time to initialize)"
  fi
else
  echo "⚠ Kafka pod not found for producer test, skipping"
fi

echo ""
echo "========================================="
echo "✅ Deployment completed successfully!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Run validation: ./scripts/validation/validate-consensus-engine.sh"
echo "2. Run integration test: ./tests/consensus-engine-integration-test.sh"
echo "3. Test pheromones: ./tests/pheromone-system-test.sh"
echo "4. View logs: kubectl logs -n ${NAMESPACE} -l app.kubernetes.io/name=consensus-engine -f"
echo "5. Port-forward API: kubectl port-forward -n ${NAMESPACE} svc/consensus-engine 8000:8000"
echo ""
