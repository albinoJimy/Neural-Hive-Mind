#!/bin/bash
set -e

# Deploy MCP Tool Catalog Service
# Segue padrão de deploy-code-forge.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "🚀 Deploying MCP Tool Catalog Service..."

# Validar pré-requisitos
echo "✓ Validando pré-requisitos..."
command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl não encontrado"; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "❌ helm não encontrado"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ docker não encontrado"; exit 1; }

# Configurações
NAMESPACE="neural-hive-mcp"
SERVICE_NAME="mcp-tool-catalog"
IMAGE_REGISTRY="${DOCKER_REGISTRY:-localhost:5000}"
IMAGE_TAG="${IMAGE_TAG:-1.0.0}"
FULL_IMAGE="${IMAGE_REGISTRY}/neural-hive-mind/${SERVICE_NAME}:${IMAGE_TAG}"

echo "  Registry: ${IMAGE_REGISTRY}"
echo "  Image: ${FULL_IMAGE}"
echo "  Namespace: ${NAMESPACE}"

# Build Docker image
echo ""
echo "🔨 Building Docker image..."
cd "${PROJECT_ROOT}/services/mcp-tool-catalog"
docker build -t "${FULL_IMAGE}" .

# Push to registry
echo ""
echo "📤 Pushing image to registry..."
docker push "${FULL_IMAGE}"

# Criar namespace se não existir
echo ""
echo "📦 Criando namespace ${NAMESPACE}..."
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# Criar secrets
echo ""
echo "🔐 Criando secrets..."
kubectl create secret generic mcp-mongodb-secret \
  --namespace="${NAMESPACE}" \
  --from-literal=username=mcp_user \
  --from-literal=password=changeme \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic mcp-redis-secret \
  --namespace="${NAMESPACE}" \
  --from-literal=password=changeme \
  --dry-run=client -o yaml | kubectl apply -f -

# Aplicar Kafka topics
echo ""
echo "📨 Aplicando Kafka topics..."
kubectl apply -f "${PROJECT_ROOT}/k8s/kafka-topics/mcp-tool-selection-requests-topic.yaml"
kubectl apply -f "${PROJECT_ROOT}/k8s/kafka-topics/mcp-tool-selection-responses-topic.yaml"

# Aguardar topics serem criados
echo "  Aguardando topics..."
sleep 5

# Deploy via Helm
echo ""
echo "⎈ Deploying via Helm..."
cd "${PROJECT_ROOT}/helm-charts/mcp-tool-catalog"

helm upgrade --install "${SERVICE_NAME}" . \
  --namespace="${NAMESPACE}" \
  --set image.repository="${IMAGE_REGISTRY}/neural-hive-mind/${SERVICE_NAME}" \
  --set image.tag="${IMAGE_TAG}" \
  --wait \
  --timeout=5m

# Aguardar pods ficarem ready
echo ""
echo "⏳ Aguardando pods ficarem ready..."
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=mcp-tool-catalog \
  -n "${NAMESPACE}" \
  --timeout=300s

# Smoke tests
echo ""
echo "🧪 Executando smoke tests..."

echo "  ✓ Health check..."
kubectl run curl-test --image=curlimages/curl:latest --rm -i --restart=Never -n "${NAMESPACE}" -- \
  curl -f http://mcp-tool-catalog:8080/health || echo "⚠️  Health check falhou"

echo "  ✓ Ready check..."
kubectl run curl-test --image=curlimages/curl:latest --rm -i --restart=Never -n "${NAMESPACE}" -- \
  curl -f http://mcp-tool-catalog:8080/ready || echo "⚠️  Ready check falhou"

echo "  ✓ Metrics check..."
kubectl run curl-test --image=curlimages/curl:latest --rm -i --restart=Never -n "${NAMESPACE}" -- \
  curl -f http://mcp-tool-catalog:9091/metrics | head -n 5 || echo "⚠️  Metrics check falhou"

# Exibir logs de startup
echo ""
echo "📋 Logs de startup (últimas 20 linhas):"
kubectl logs -l app.kubernetes.io/name=mcp-tool-catalog -n "${NAMESPACE}" --tail=20

# Exibir status
echo ""
echo "📊 Status do deployment:"
kubectl get pods,svc -l app.kubernetes.io/name=mcp-tool-catalog -n "${NAMESPACE}"

echo ""
echo "✅ Deploy concluído com sucesso!"
echo ""
echo "📍 Instruções de acesso:"
echo "   - Health: kubectl port-forward -n ${NAMESPACE} svc/mcp-tool-catalog 8080:8080"
echo "   - Metrics: kubectl port-forward -n ${NAMESPACE} svc/mcp-tool-catalog 9091:9091"
echo "   - Logs: kubectl logs -f -l app.kubernetes.io/name=mcp-tool-catalog -n ${NAMESPACE}"
echo ""
echo "🔍 Validar instalação: ./scripts/validation/validate-mcp-tool-catalog.sh"
