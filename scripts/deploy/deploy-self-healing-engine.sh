#!/bin/bash
set -e

# Self-Healing Engine Deployment Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configurações
NAMESPACE="neural-hive-resilience"
SKIP_BUILD=false
SKIP_PUSH=false
DRY_RUN=false
IMAGE_TAG="${IMAGE_TAG:-latest}"
REGISTRY="${DOCKER_REGISTRY:-neural-hive}"

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-build) SKIP_BUILD=true; shift ;;
    --skip-push) SKIP_PUSH=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --tag) IMAGE_TAG="$2"; shift 2 ;;
    *) echo "Argumento desconhecido: $1"; exit 1 ;;
  esac
done

echo -e "${GREEN}=== Self-Healing Engine Deployment ===${NC}"

# Validar
echo -e "${YELLOW}1. Validando pré-requisitos...${NC}"
command -v kubectl >/dev/null 2>&1 || { echo -e "${RED}kubectl não encontrado${NC}"; exit 1; }
command -v helm >/dev/null 2>&1 || { echo -e "${RED}helm não encontrado${NC}"; exit 1; }
echo -e "${GREEN}✓ Pré-requisitos OK${NC}"

# Namespace
echo -e "${YELLOW}2. Criando namespace...${NC}"
[ "$DRY_RUN" = false ] && kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓ Namespace OK${NC}"

# Build
if [ "$SKIP_BUILD" = false ]; then
  echo -e "${YELLOW}3. Building image...${NC}"
  if [ "$DRY_RUN" = false ]; then
    cd "$PROJECT_ROOT/services/self-healing-engine"
    docker build -t "$REGISTRY/self-healing-engine:$IMAGE_TAG" .
  fi
  echo -e "${GREEN}✓ Image built${NC}"
fi

# Push
if [ "$SKIP_PUSH" = false ]; then
  echo -e "${YELLOW}4. Pushing image...${NC}"
  [ "$DRY_RUN" = false ] && docker push "$REGISTRY/self-healing-engine:$IMAGE_TAG"
  echo -e "${GREEN}✓ Image pushed${NC}"
fi

# Deploy
echo -e "${YELLOW}5. Deploying Helm chart...${NC}"
if [ "$DRY_RUN" = false ]; then
  helm upgrade --install self-healing-engine "$PROJECT_ROOT/helm-charts/self-healing-engine" \
    --namespace $NAMESPACE --set image.tag=$IMAGE_TAG --wait --timeout 5m
else
  helm upgrade --install self-healing-engine "$PROJECT_ROOT/helm-charts/self-healing-engine" \
    --namespace $NAMESPACE --set image.tag=$IMAGE_TAG --dry-run
fi
echo -e "${GREEN}✓ Helm deployed${NC}"

# Wait
if [ "$DRY_RUN" = false ]; then
  echo -e "${YELLOW}6. Aguardando pods...${NC}"
  kubectl wait --for=condition=ready pod -l app=self-healing-engine -n $NAMESPACE --timeout=300s
  echo -e "${GREEN}✓ Pods ready${NC}"
fi

# Health
if [ "$DRY_RUN" = false ]; then
  echo -e "${YELLOW}7. Validando health...${NC}"
  POD=$(kubectl get pods -n $NAMESPACE -l app=self-healing-engine -o jsonpath='{.items[0].metadata.name}')
  kubectl exec -n $NAMESPACE $POD -- curl -f http://localhost:8080/health || {
    echo -e "${RED}Health falhou${NC}"; exit 1;
  }
  echo -e "${GREEN}✓ Health OK${NC}"
fi

echo -e "${GREEN}=== Deploy concluído! ===${NC}"
