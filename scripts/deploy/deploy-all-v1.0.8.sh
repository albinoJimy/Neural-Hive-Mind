#!/bin/bash
set -euo pipefail

# Deploy v1.0.8 via Helm no Kubernetes
# Uso: ./scripts/deploy/deploy-all-v1.0.8.sh

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deploy v1.0.8 - Timestamp Fix${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Configuração
VERSION="1.0.8"
NAMESPACE="${NAMESPACE:-neural-hive}"
REGISTRY="${REGISTRY:-neural-hive-mind}"

# Diretório do projeto
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}Diretório do projeto:${NC} $PROJECT_ROOT"
echo -e "${BLUE}Versão:${NC} $VERSION"
echo -e "${BLUE}Namespace:${NC} $NAMESPACE"
echo -e "${BLUE}Registry:${NC} $REGISTRY"
echo ""

# Componentes para deploy
SPECIALISTS=(
    "business"
    "technical"
    "behavior"
    "evolution"
    "architecture"
)

# Validação de pré-requisitos
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}VALIDAÇÃO DE PRÉ-REQUISITOS${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Verificar kubectl
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}✗ kubectl não encontrado${NC}"
    exit 1
fi
echo -e "${GREEN}✓ kubectl encontrado${NC}"

# Verificar helm
if ! command -v helm &> /dev/null; then
    echo -e "${RED}✗ helm não encontrado${NC}"
    exit 1
fi
echo -e "${GREEN}✓ helm encontrado${NC}"

# Verificar cluster
if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}✗ Cluster Kubernetes não acessível${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Cluster Kubernetes acessível${NC}"

# Verificar namespace
if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
    echo -e "${YELLOW}⚠ Namespace $NAMESPACE não existe, criando...${NC}"
    kubectl create namespace "$NAMESPACE"
fi
echo -e "${GREEN}✓ Namespace $NAMESPACE existe${NC}"

echo ""

# Verificar imagens Docker
echo -e "${BLUE}Verificando imagens Docker...${NC}"
MISSING_IMAGES=()

for specialist in "${SPECIALISTS[@]}"; do
    IMAGE="${REGISTRY}/specialist-${specialist}:${VERSION}"
    if ! docker images | grep -q "specialist-${specialist}.*${VERSION}"; then
        MISSING_IMAGES+=("$IMAGE")
    fi
done

if ! docker images | grep -q "consensus-engine.*${VERSION}"; then
    MISSING_IMAGES+=("${REGISTRY}/consensus-engine:${VERSION}")
fi

if [ ${#MISSING_IMAGES[@]} -gt 0 ]; then
    echo -e "${YELLOW}⚠ Imagens faltando (rode build primeiro):${NC}"
    for img in "${MISSING_IMAGES[@]}"; do
        echo -e "  ${YELLOW}⚠${NC} $img"
    done
    echo ""
    echo -e "${YELLOW}Execute: ./scripts/build/build-all-v1.0.8.sh${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Todas as imagens Docker encontradas${NC}"
echo ""

# Importar imagens para containerd (kind)
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}IMPORTAR IMAGENS PARA CONTAINERD${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Verificar se é kind
if kubectl config current-context | grep -q "kind"; then
    echo -e "${BLUE}Cluster kind detectado, importando imagens...${NC}"

    CLUSTER_NAME=$(kubectl config current-context | sed 's/kind-//')

    for specialist in "${SPECIALISTS[@]}"; do
        IMAGE="${REGISTRY}/specialist-${specialist}:${VERSION}"
        echo -e "${YELLOW}Importando: $IMAGE${NC}"
        kind load docker-image "$IMAGE" --name "$CLUSTER_NAME"
    done

    echo -e "${YELLOW}Importando: ${REGISTRY}/consensus-engine:${VERSION}${NC}"
    kind load docker-image "${REGISTRY}/consensus-engine:${VERSION}" --name "$CLUSTER_NAME"

    echo -e "${GREEN}✓ Imagens importadas para kind${NC}"
else
    echo -e "${BLUE}Não é cluster kind, pulando importação...${NC}"
fi
echo ""

# Contadores
SUCCESS_COUNT=0
FAILED_COUNT=0
FAILED_COMPONENTS=()

# Deploy dos Specialists
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}DEPLOY DOS SPECIALISTS${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

for specialist in "${SPECIALISTS[@]}"; do
    CHART_NAME="specialist-${specialist}"
    CHART_PATH="helm-charts/${CHART_NAME}"
    VALUES_FILE="${CHART_PATH}/values-k8s.yaml"

    echo -e "${GREEN}----------------------------------------${NC}"
    echo -e "${GREEN}Deploying: $CHART_NAME${NC}"
    echo -e "${GREEN}----------------------------------------${NC}"

    # Verificar se chart existe
    if [ ! -d "$CHART_PATH" ]; then
        echo -e "${RED}✗ Chart não encontrado: $CHART_PATH${NC}"
        FAILED_COUNT=$((FAILED_COUNT + 1))
        FAILED_COMPONENTS+=("$CHART_NAME")
        continue
    fi

    # Deploy via Helm
    echo -e "${YELLOW}Chart:${NC} $CHART_PATH"
    echo -e "${YELLOW}Values:${NC} $VALUES_FILE"
    echo ""

    helm upgrade --install "$CHART_NAME" "$CHART_PATH" \
        --namespace "$NAMESPACE" \
        --values "$VALUES_FILE" \
        --set image.repository="${REGISTRY}/${CHART_NAME}" \
        --set image.tag="${VERSION}" \
        --wait \
        --timeout 5m

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Deploy completo: $CHART_NAME${NC}"

        # Aguardar pods ficarem ready
        echo -e "${BLUE}Aguardando pod ficar ready...${NC}"
        kubectl wait --for=condition=ready pod \
            -l "app=${CHART_NAME}" \
            -n "$NAMESPACE" \
            --timeout=300s

        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ Pod ready: $CHART_NAME${NC}"
            SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        else
            echo -e "${YELLOW}⚠ Timeout aguardando pod: $CHART_NAME${NC}"
        fi

        # Mostrar status do pod
        kubectl get pods -n "$NAMESPACE" -l "app=${CHART_NAME}"
    else
        echo -e "${RED}✗ Falha no deploy: $CHART_NAME${NC}"
        FAILED_COUNT=$((FAILED_COUNT + 1))
        FAILED_COMPONENTS+=("$CHART_NAME")
    fi

    echo ""
done

# Deploy do Consensus Engine
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}DEPLOY DO CONSENSUS ENGINE${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

CHART_NAME="consensus-engine"
CHART_PATH="helm-charts/${CHART_NAME}"
VALUES_FILE="${CHART_PATH}/values.yaml"

echo -e "${YELLOW}Chart:${NC} $CHART_PATH"
echo -e "${YELLOW}Values:${NC} $VALUES_FILE"
echo ""

helm upgrade --install "$CHART_NAME" "$CHART_PATH" \
    --namespace "$NAMESPACE" \
    --values "$VALUES_FILE" \
    --set image.repository="${REGISTRY}/${CHART_NAME}" \
    --set image.tag="${VERSION}" \
    --wait \
    --timeout 5m

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Deploy completo: $CHART_NAME${NC}"

    # Aguardar pods ficarem ready
    echo -e "${BLUE}Aguardando pods ficarem ready...${NC}"
    kubectl wait --for=condition=ready pod \
        -l "app=${CHART_NAME}" \
        -n "$NAMESPACE" \
        --timeout=300s

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Pods ready: $CHART_NAME${NC}"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        echo -e "${YELLOW}⚠ Timeout aguardando pods: $CHART_NAME${NC}"
    fi

    # Mostrar status dos pods
    kubectl get pods -n "$NAMESPACE" -l "app=${CHART_NAME}"
else
    echo -e "${RED}✗ Falha no deploy: $CHART_NAME${NC}"
    FAILED_COUNT=$((FAILED_COUNT + 1))
    FAILED_COMPONENTS+=("$CHART_NAME")
fi

echo ""

# Validação pós-deploy
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}VALIDAÇÃO PÓS-DEPLOY${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

echo -e "${BLUE}Verificando versões deployadas:${NC}"
kubectl get pods -n "$NAMESPACE" -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[0].image}{"\n"}{end}' | grep -E "specialist|consensus"
echo ""

echo -e "${BLUE}Verificando pods com v${VERSION}:${NC}"
PODS_WITH_VERSION=$(kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[*].spec.containers[0].image}' | tr ' ' '\n' | grep -c "${VERSION}" || echo "0")
TOTAL_EXPECTED=$((${#SPECIALISTS[@]} + 1))  # 5 specialists + 1 consensus-engine
echo -e "Pods com v${VERSION}: ${PODS_WITH_VERSION}/${TOTAL_EXPECTED}"

if [ "$PODS_WITH_VERSION" -eq "$TOTAL_EXPECTED" ]; then
    echo -e "${GREEN}✓ Todas as versões corretas${NC}"
else
    echo -e "${YELLOW}⚠ Algumas versões podem estar incorretas${NC}"
fi
echo ""

# Verificar logs para TypeError
echo -e "${BLUE}Verificando logs do consensus-engine (últimas 50 linhas):${NC}"
CONSENSUS_POD=$(kubectl get pods -n "$NAMESPACE" -l "app=consensus-engine" -o jsonpath='{.items[0].metadata.name}')
if [ -n "$CONSENSUS_POD" ]; then
    kubectl logs -n "$NAMESPACE" "$CONSENSUS_POD" --tail=50 | grep -i "typeerror\|evaluated_at" | head -10 || echo "Nenhum TypeError encontrado"
else
    echo -e "${YELLOW}⚠ Pod consensus-engine não encontrado${NC}"
fi
echo ""

# Resumo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}RESUMO DO DEPLOY${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

TOTAL_COMPONENTS=$((${#SPECIALISTS[@]} + 1))
echo -e "${GREEN}Sucesso:${NC} $SUCCESS_COUNT/${TOTAL_COMPONENTS}"
echo -e "${RED}Falhas:${NC} $FAILED_COUNT/${TOTAL_COMPONENTS}"
echo ""

if [ $FAILED_COUNT -gt 0 ]; then
    echo -e "${RED}Componentes com falha:${NC}"
    for failed in "${FAILED_COMPONENTS[@]}"; do
        echo -e "  ${RED}✗${NC} $failed"
    done
    echo ""
fi

echo -e "${BLUE}Status dos pods:${NC}"
kubectl get pods -n "$NAMESPACE" -l "app in (specialist-business,specialist-technical,specialist-behavior,specialist-evolution,specialist-architecture,consensus-engine)"
echo ""

if [ $FAILED_COUNT -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ DEPLOY COMPLETO v${VERSION}${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${YELLOW}Próximo passo:${NC}"
    echo -e "  python test-timestamp-fix-e2e.py"
    echo ""
    exit 0
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ DEPLOY FALHOU${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    exit 1
fi
