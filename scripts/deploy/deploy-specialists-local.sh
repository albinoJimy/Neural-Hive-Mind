#!/bin/bash

# Deploy all neural specialists to local Minikube cluster
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
FORCE_DEPLOY="${FORCE_DEPLOY:-false}"
SPECIALISTS=("business" "technical" "behavior" "evolution" "architecture")

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deploying Neural Specialists (Local)${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Navigate to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# Validate prerequisites
echo -e "${YELLOW}Validating prerequisites...${NC}"

# Check Minikube is running
if ! minikube status &>/dev/null; then
  echo -e "${RED}✗ Minikube is not running${NC}"
  echo -e "${YELLOW}Start Minikube with: minikube start${NC}"
  exit 1
fi
echo -e "${GREEN}✓ Minikube is running${NC}"

# Check kubectl is configured
if ! kubectl cluster-info &>/dev/null; then
  echo -e "${RED}✗ kubectl is not configured${NC}"
  exit 1
fi
echo -e "${GREEN}✓ kubectl is configured${NC}"

# Check if images are built
eval $(minikube docker-env)
MISSING_IMAGES=0
for specialist in "${SPECIALISTS[@]}"; do
  if ! docker images | grep -q "neural-hive/specialist-${specialist}"; then
    echo -e "${YELLOW}⚠ Image not found: neural-hive/specialist-${specialist}:local${NC}"
    MISSING_IMAGES=$((MISSING_IMAGES + 1))
  fi
done

if [ $MISSING_IMAGES -gt 0 ]; then
  echo -e "${YELLOW}⚠ $MISSING_IMAGES specialist images missing${NC}"
  echo -e "${YELLOW}Run: ./scripts/deploy/build-specialists-images.sh${NC}"
  read -p "Continue anyway? (y/n) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
  fi
else
  echo -e "${GREEN}✓ All specialist images found${NC}"
fi

echo ""

# Export environment variables for local deployment
echo -e "${YELLOW}Configuring environment variables...${NC}"
export MLFLOW_TRACKING_URI="http://mlflow.mlflow.svc.cluster.local:5000"
export MONGODB_URI="mongodb://mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive"
export NEO4J_PASSWORD="neo4j"
export REDIS_PASSWORD=""

echo -e "${GREEN}✓ Environment configured${NC}"
echo "  MLFLOW_TRACKING_URI: $MLFLOW_TRACKING_URI"
echo "  MONGODB_URI: $MONGODB_URI"
echo "  NEO4J_PASSWORD: ***"
echo "  REDIS_PASSWORD: (empty)"
echo ""

# Deploy counter
SUCCESS_COUNT=0
FAILED_COUNT=0
FAILED_SPECIALISTS=()

# Deploy each specialist
for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  RELEASE_NAME="specialist-${specialist}"
  CHART_PATH="./helm-charts/specialist-${specialist}"
  VALUES_FILE="./helm-charts/specialist-${specialist}/values-local.yaml"

  echo -e "${GREEN}========================================${NC}"
  echo -e "${GREEN}Deploying: specialist-${specialist}${NC}"
  echo -e "${GREEN}========================================${NC}"

  # Check if chart exists
  if [ ! -d "$CHART_PATH" ]; then
    echo -e "${RED}✗ Helm chart not found: $CHART_PATH${NC}"
    FAILED_COUNT=$((FAILED_COUNT + 1))
    FAILED_SPECIALISTS+=("$specialist (chart missing)")
    echo ""
    continue
  fi

  # Check if values file exists
  if [ ! -f "$VALUES_FILE" ]; then
    echo -e "${YELLOW}⚠ Values file not found: $VALUES_FILE${NC}"
    echo -e "${YELLOW}Using default values${NC}"
    VALUES_FILE=""
  fi

  # Create namespace
  echo -e "${YELLOW}Creating namespace: $NAMESPACE${NC}"
  kubectl create namespace "$NAMESPACE" \
    --dry-run=client -o yaml | \
    kubectl apply -f -

  kubectl label namespace "$NAMESPACE" \
    "neural-hive.io/component=${specialist}-specialist" \
    "neural-hive.io/layer=cognitiva" \
    --overwrite

  echo -e "${GREEN}✓ Namespace ready${NC}"

  # Create secret
  echo -e "${YELLOW}Creating specialist-secrets...${NC}"
  kubectl create secret generic specialist-secrets \
    --from-literal=mlflow_tracking_uri="$MLFLOW_TRACKING_URI" \
    --from-literal=mongodb_uri="$MONGODB_URI" \
    --from-literal=neo4j_password="$NEO4J_PASSWORD" \
    --from-literal=redis_password="$REDIS_PASSWORD" \
    --namespace="$NAMESPACE" \
    --dry-run=client -o yaml | kubectl apply -f -

  echo -e "${GREEN}✓ Secret created${NC}"

  # Force uninstall if requested
  if [ "$FORCE_DEPLOY" = "true" ]; then
    echo -e "${YELLOW}Force deploy: uninstalling existing release...${NC}"
    helm uninstall "$RELEASE_NAME" --namespace "$NAMESPACE" &>/dev/null || true
  fi

  # Deploy with Helm
  echo -e "${YELLOW}Deploying via Helm...${NC}"
  HELM_CMD="helm upgrade --install $RELEASE_NAME $CHART_PATH \
    --namespace $NAMESPACE \
    --create-namespace \
    --wait \
    --timeout 10m"

  if [ -n "$VALUES_FILE" ]; then
    HELM_CMD="$HELM_CMD --values $VALUES_FILE"
  fi

  if eval $HELM_CMD; then
    echo -e "${GREEN}✓ Helm deployment successful${NC}"

    # Wait for rollout
    echo -e "${YELLOW}Waiting for rollout to complete...${NC}"
    if kubectl rollout status deployment/"$RELEASE_NAME" -n "$NAMESPACE" --timeout=5m; then
      echo -e "${GREEN}✓ Rollout complete${NC}"
      SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
      echo -e "${RED}✗ Rollout failed${NC}"
      echo -e "${YELLOW}Pod status:${NC}"
      kubectl get pods -n "$NAMESPACE"
      echo -e "${YELLOW}Recent events:${NC}"
      kubectl get events -n "$NAMESPACE" --sort-by='.lastTimestamp' | tail -10
      FAILED_COUNT=$((FAILED_COUNT + 1))
      FAILED_SPECIALISTS+=("$specialist (rollout timeout)")
    fi
  else
    echo -e "${RED}✗ Helm deployment failed${NC}"
    FAILED_COUNT=$((FAILED_COUNT + 1))
    FAILED_SPECIALISTS+=("$specialist (helm error)")
  fi

  echo ""
done

# Final validation
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Validating Deployments${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

for specialist in "${SPECIALISTS[@]}"; do
  NAMESPACE="specialist-${specialist}"
  echo -e "${YELLOW}Checking specialist-${specialist}...${NC}"

  if kubectl wait --for=condition=ready pod \
    -l "app.kubernetes.io/name=specialist-${specialist}" \
    -n "$NAMESPACE" \
    --timeout=2m &>/dev/null; then
    echo -e "${GREEN}✓ Pod ready${NC}"
  else
    echo -e "${RED}✗ Pod not ready${NC}"
  fi
done

echo ""

# Deployment summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Summary${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Successful deployments: ${GREEN}$SUCCESS_COUNT${NC}/5"
echo -e "Failed deployments: ${RED}$FAILED_COUNT${NC}/5"
echo ""

if [ $FAILED_COUNT -gt 0 ]; then
  echo -e "${RED}Failed specialists:${NC}"
  for failed in "${FAILED_SPECIALISTS[@]}"; do
    echo -e "${RED}  - $failed${NC}"
  done
  echo ""
fi

# List all specialist resources
echo -e "${YELLOW}Deployed resources:${NC}"
echo ""
kubectl get pods,svc -A | grep -E "NAMESPACE|specialist-"
echo ""

if [ $FAILED_COUNT -gt 0 ]; then
  echo -e "${RED}Deployment completed with errors${NC}"
  exit 1
else
  echo -e "${GREEN}All specialists deployed successfully!${NC}"
  echo ""
  echo -e "${YELLOW}Next steps:${NC}"
  echo "  1. Validate deployment: ./scripts/validation/validate-specialists-deployment.sh"
  echo "  2. Test HTTP endpoints: ./scripts/test/test-specialist-http.sh business"
  echo "  3. Test gRPC endpoints: ./scripts/test/test-specialist-grpc.sh technical"
  echo "  4. Run integration tests: ./scripts/test/test-specialists-integration.sh"
  echo ""
  exit 0
fi
