#!/bin/bash
# Deploy MCP Servers para Neural Hive-Mind
# Uso: ./scripts/deploy-mcp-servers.sh [--local] [--build] [--tag TAG]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
NAMESPACE="neural-hive-mcp"
REGISTRY="37.60.241.150:30500"
VALUES_FILE="values.yaml"
BUILD_IMAGES=false
TAG="1.0.0"

# Parse argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --local)
            VALUES_FILE="values-local.yaml"
            shift
            ;;
        --build)
            BUILD_IMAGES=true
            shift
            ;;
        --tag)
            TAG="$2"
            shift 2
            ;;
        *)
            echo "Argumento desconhecido: $1"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "Deploy MCP Servers - Neural Hive-Mind"
echo "=========================================="
echo "Namespace: $NAMESPACE"
echo "Values: $VALUES_FILE"
echo "Build Images: $BUILD_IMAGES"
echo "Tag: $TAG"
echo ""

# Criar namespace
echo "Criando namespace $NAMESPACE..."
kubectl apply -f "$PROJECT_ROOT/k8s/namespaces/neural-hive-mcp-namespace.yaml"

# Build images se solicitado
if [ "$BUILD_IMAGES" = true ]; then
    echo ""
    echo "=========================================="
    echo "Building Docker Images"
    echo "=========================================="

    # Use dedicated build script with parent context approach
    MCP_REGISTRY="$REGISTRY" MCP_TAG="$TAG" "$SCRIPT_DIR/build-mcp-servers.sh" --push
fi

# Update helm dependencies
echo ""
echo "=========================================="
echo "Updating Helm Dependencies"
echo "=========================================="

for server in trivy-mcp-server sonarqube-mcp-server ai-codegen-mcp-server; do
    echo "Updating dependencies for $server..."
    helm dependency update "$PROJECT_ROOT/helm-charts/mcp-servers/$server" 2>/dev/null || true
done

# Deploy Trivy MCP Server
echo ""
echo "=========================================="
echo "Deploying Trivy MCP Server"
echo "=========================================="

helm upgrade --install trivy-mcp-server \
    "$PROJECT_ROOT/helm-charts/mcp-servers/trivy-mcp-server" \
    --namespace "$NAMESPACE" \
    --values "$PROJECT_ROOT/helm-charts/mcp-servers/trivy-mcp-server/$VALUES_FILE" \
    --wait --timeout=5m

echo "Trivy MCP Server deployed!"

# Deploy SonarQube MCP Server
echo ""
echo "=========================================="
echo "Deploying SonarQube MCP Server"
echo "=========================================="

helm upgrade --install sonarqube-mcp-server \
    "$PROJECT_ROOT/helm-charts/mcp-servers/sonarqube-mcp-server" \
    --namespace "$NAMESPACE" \
    --values "$PROJECT_ROOT/helm-charts/mcp-servers/sonarqube-mcp-server/$VALUES_FILE" \
    --wait --timeout=5m

echo "SonarQube MCP Server deployed!"

# Deploy AI CodeGen MCP Server
echo ""
echo "=========================================="
echo "Deploying AI CodeGen MCP Server"
echo "=========================================="

helm upgrade --install ai-codegen-mcp-server \
    "$PROJECT_ROOT/helm-charts/mcp-servers/ai-codegen-mcp-server" \
    --namespace "$NAMESPACE" \
    --values "$PROJECT_ROOT/helm-charts/mcp-servers/ai-codegen-mcp-server/$VALUES_FILE" \
    --wait --timeout=5m

echo "AI CodeGen MCP Server deployed!"

# Verificar status
echo ""
echo "=========================================="
echo "Verificando Status"
echo "=========================================="

kubectl get pods -n "$NAMESPACE"
echo ""
kubectl get services -n "$NAMESPACE"

echo ""
echo "=========================================="
echo "MCP Servers deployed successfully!"
echo "=========================================="
echo ""
echo "Endpoints internos:"
echo "  - Trivy: http://trivy-mcp-server.$NAMESPACE.svc.cluster.local:3000"
echo "  - SonarQube: http://sonarqube-mcp-server.$NAMESPACE.svc.cluster.local:3000"
echo "  - AI CodeGen: http://ai-codegen-mcp-server.$NAMESPACE.svc.cluster.local:3000"
echo ""
echo "Para testar localmente, use port-forward:"
echo "  kubectl port-forward -n $NAMESPACE svc/trivy-mcp-server 3000:3000"
