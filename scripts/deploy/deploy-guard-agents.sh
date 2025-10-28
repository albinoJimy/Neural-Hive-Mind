#!/bin/bash
set -e

# Guard Agents Deployment Script
# Este script implementa o deploy completo do Guard Agents no Kubernetes

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configurações padrão
NAMESPACE="neural-hive-resilience"
SKIP_BUILD=false
SKIP_PUSH=false
DRY_RUN=false
IMAGE_TAG="${IMAGE_TAG:-latest}"
REGISTRY="${DOCKER_REGISTRY:-neural-hive}"

# Parse argumentos
while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-build)
      SKIP_BUILD=true
      shift
      ;;
    --skip-push)
      SKIP_PUSH=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    --tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    *)
      echo "Argumento desconhecido: $1"
      exit 1
      ;;
  esac
done

echo -e "${GREEN}=== Guard Agents Deployment ===${NC}"
echo "Namespace: $NAMESPACE"
echo "Image Tag: $IMAGE_TAG"
echo ""

# Validar pré-requisitos
echo -e "${YELLOW}1. Validando pré-requisitos...${NC}"
command -v kubectl >/dev/null 2>&1 || { echo -e "${RED}kubectl não encontrado${NC}"; exit 1; }
command -v helm >/dev/null 2>&1 || { echo -e "${RED}helm não encontrado${NC}"; exit 1; }
kubectl cluster-info >/dev/null 2>&1 || { echo -e "${RED}Cluster Kubernetes não acessível${NC}"; exit 1; }
echo -e "${GREEN}✓ Pré-requisitos OK${NC}"

# Criar namespace
echo -e "${YELLOW}2. Criando namespace...${NC}"
if [ "$DRY_RUN" = false ]; then
  kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
fi
echo -e "${GREEN}✓ Namespace criado/verificado${NC}"

# Aplicar Kafka topics
echo -e "${YELLOW}3. Aplicando Kafka topics...${NC}"
if [ "$DRY_RUN" = false ]; then
  kubectl apply -f "$PROJECT_ROOT/k8s/kafka-topics/security-incidents-topic.yaml"
  kubectl apply -f "$PROJECT_ROOT/k8s/kafka-topics/remediation-actions-topic.yaml"
fi
echo -e "${GREEN}✓ Kafka topics aplicados${NC}"

# Build Docker image
if [ "$SKIP_BUILD" = false ]; then
  echo -e "${YELLOW}4. Building Docker image...${NC}"
  if [ "$DRY_RUN" = false ]; then
    cd "$PROJECT_ROOT/services/guard-agents"
    docker build -t "$REGISTRY/guard-agents:$IMAGE_TAG" .
  fi
  echo -e "${GREEN}✓ Image built${NC}"
else
  echo -e "${YELLOW}4. Skipping build (--skip-build)${NC}"
fi

# Push Docker image
if [ "$SKIP_PUSH" = false ]; then
  echo -e "${YELLOW}5. Pushing Docker image...${NC}"
  if [ "$DRY_RUN" = false ]; then
    docker push "$REGISTRY/guard-agents:$IMAGE_TAG"
  fi
  echo -e "${GREEN}✓ Image pushed${NC}"
else
  echo -e "${YELLOW}5. Skipping push (--skip-push)${NC}"
fi

# Deploy Helm chart
echo -e "${YELLOW}6. Deploying Helm chart...${NC}"
if [ "$DRY_RUN" = false ]; then
  helm upgrade --install guard-agents "$PROJECT_ROOT/helm-charts/guard-agents" \
    --namespace $NAMESPACE \
    --set image.tag=$IMAGE_TAG \
    --wait \
    --timeout 5m
else
  helm upgrade --install guard-agents "$PROJECT_ROOT/helm-charts/guard-agents" \
    --namespace $NAMESPACE \
    --set image.tag=$IMAGE_TAG \
    --dry-run
fi
echo -e "${GREEN}✓ Helm chart deployed${NC}"

# Aguardar pods ficarem ready
if [ "$DRY_RUN" = false ]; then
  echo -e "${YELLOW}7. Aguardando pods ficarem ready...${NC}"
  kubectl wait --for=condition=ready pod -l app=guard-agents -n $NAMESPACE --timeout=300s
  echo -e "${GREEN}✓ Pods ready${NC}"
fi

# Validar health checks
if [ "$DRY_RUN" = false ]; then
  echo -e "${YELLOW}8. Validando health checks...${NC}"
  POD=$(kubectl get pods -n $NAMESPACE -l app=guard-agents -o jsonpath='{.items[0].metadata.name}')
  kubectl exec -n $NAMESPACE $POD -- curl -f http://localhost:8080/health/liveness || {
    echo -e "${RED}Health check falhou${NC}"
    exit 1
  }
  echo -e "${GREEN}✓ Health checks OK${NC}"
fi

# Exibir logs iniciais
if [ "$DRY_RUN" = false ]; then
  echo -e "${YELLOW}9. Logs iniciais:${NC}"
  kubectl logs -n $NAMESPACE -l app=guard-agents --tail=20
fi

echo ""
echo -e "${GREEN}=== Deploy concluído com sucesso! ===${NC}"
echo ""
echo "Comandos úteis:"
echo "  kubectl get pods -n $NAMESPACE -l app=guard-agents"
echo "  kubectl logs -n $NAMESPACE -l app=guard-agents -f"
echo "  kubectl port-forward -n $NAMESPACE svc/guard-agents 8080:8080"
echo "  kubectl port-forward -n $NAMESPACE svc/guard-agents 9090:9090  # metrics"
