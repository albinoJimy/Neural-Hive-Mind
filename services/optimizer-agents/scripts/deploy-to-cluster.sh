#!/bin/bash
set -e

# Deploy do Optimizer Agents em cluster Kubernetes
# Uso: ./scripts/deploy-to-cluster.sh [namespace] [environment]

NAMESPACE=${1:-neural-hive-orchestration}
ENVIRONMENT=${2:-production}
REGISTRY="37.60.241.150:30500"
VERSION=${VERSION:-$(git rev-parse --short HEAD)}
IMAGE_NAME="${REGISTRY}/optimizer-agents"

echo "=== Deploy Optimizer Agents ==="
echo "Namespace: $NAMESPACE"
echo "Environment: $ENVIRONMENT"
echo "Version: $VERSION"
echo ""

# 1. Build da imagem Docker
echo "[1/6] Build da imagem Docker..."
docker build -t ${IMAGE_NAME}:${VERSION} -f Dockerfile ../..
docker tag ${IMAGE_NAME}:${VERSION} ${IMAGE_NAME}:latest

# 2. Push da imagem
echo "[2/6] Push da imagem..."
docker push ${IMAGE_NAME}:${VERSION}
docker push ${IMAGE_NAME}:latest

# 3. Atualizar values.yaml com a versão
echo "[3/6] Atualizando values.yaml..."
sed -i.bak "s/tag: \".*\"/tag: \"$VERSION\"/" helm-chart/values.yaml

# 4. Instalar/atualizar Helm release
echo "[4/6] Deploy Helm..."
helm upgrade --install optimizer-agents ./helm-chart \
    --namespace $NAMESPACE \
    --create-namespace \
    --set image.tag=$VERSION \
    --set env.ENVIRONMENT=$ENVIRONMENT \
    --wait \
    --timeout 5m

# 5. Restaurar values.yaml
echo "[5/6] Restaurando values.yaml..."
mv helm-chart/values.yaml.bak helm-chart/values.yaml

# 6. Verificar deploy
echo "[6/6] Verificando deploy..."
kubectl get pods -n $NAMESPACE -l app=optimizer-agents
kubectl get svc -n $NAMESPACE optimizer-agents

echo ""
echo "✅ Deploy completo!"
echo ""
echo "Para validar, execute:"
echo "  ./scripts/validate-deployment.sh"
