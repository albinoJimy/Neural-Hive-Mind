#!/bin/bash
set -eo pipefail

echo "=========================================="
echo "Deploy dos Componentes Faltantes - Fase 1"
echo "Data: $(date)"
if [ -n "${ONLY:-}" ]; then
    echo "Modo filtrado: Deployando apenas ${ONLY}"
fi
echo "=========================================="
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Componentes a deployar
if [ -n "${ONLY:-}" ]; then
    COMPONENTS=("$ONLY")
else
    COMPONENTS=(
        "semantic-translation-engine"
        "consensus-engine"
        "memory-layer-api"
        "worker-agents"
        "specialist-business"
    )
fi

# Função para deploy de um componente
deploy_component() {
    local COMPONENT=$1
    local NAMESPACE=$COMPONENT

    # Override namespace para componentes específicos
    case "$COMPONENT" in
        "worker-agents")
            NAMESPACE="neural-hive-execution"
            ;;
        "specialist-business")
            NAMESPACE="specialist-business"
            ;;
    esac

    local CHART_PATH="./helm-charts/$COMPONENT"
    local VALUES_FILE="$CHART_PATH/values-local.yaml"

    echo -e "${BLUE}=========================================="
    echo "Deployando: $COMPONENT"
    echo "==========================================${NC}"

    # 1. Criar namespace
    echo -e "${BLUE}ℹ${NC} Criando namespace $NAMESPACE..."
    kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

    # 2. Aplicar labels
    echo -e "${BLUE}ℹ${NC} Aplicando labels no namespace..."
    kubectl label namespace $NAMESPACE \
        neural-hive.io/component=$COMPONENT \
        neural-hive.io/layer=conhecimento-dados \
        --overwrite

    # 3. Verificar se o chart existe
    if [ ! -f "$CHART_PATH/Chart.yaml" ]; then
        echo -e "${RED}✗${NC} Chart não encontrado: $CHART_PATH"
        return 1
    fi

    # 4. Verificar se o values file existe
    if [ ! -f "$VALUES_FILE" ]; then
        echo -e "${YELLOW}⚠${NC} Values file não encontrado: $VALUES_FILE"
        echo -e "${BLUE}ℹ${NC} Usando values.yaml padrão..."
        VALUES_FILE="$CHART_PATH/values.yaml"
    fi

    # 5. Deploy via Helm
    echo -e "${BLUE}ℹ${NC} Deployando Helm chart..."
    if helm upgrade --install $COMPONENT $CHART_PATH \
        --namespace $NAMESPACE \
        --values $VALUES_FILE \
        --wait --timeout 5m; then
        echo -e "${GREEN}✓${NC} Helm chart instalado com sucesso"
    else
        echo -e "${RED}✗${NC} Falha ao instalar Helm chart"
        return 1
    fi

    # 6. Verificar deployment
    echo -e "${BLUE}ℹ${NC} Verificando deployment..."
    if kubectl get deployment -n $NAMESPACE $COMPONENT &> /dev/null; then
        kubectl rollout status deployment/$COMPONENT -n $NAMESPACE --timeout=3m || true
    else
        echo -e "${YELLOW}⚠${NC} Deployment não encontrado (pode ser StatefulSet ou DaemonSet)"
    fi

    # 7. Listar pods
    echo -e "${BLUE}ℹ${NC} Pods do $COMPONENT:"
    kubectl get pods -n $NAMESPACE

    echo -e "${GREEN}✓${NC} Deploy do $COMPONENT concluído"
    echo ""
}

# Deploy de cada componente
TOTAL=${#COMPONENTS[@]}
SUCCESS=0
FAILED=0

for component in "${COMPONENTS[@]}"; do
    if deploy_component "$component"; then
        ((SUCCESS++))
    else
        ((FAILED++))
        echo -e "${RED}✗${NC} Falha ao deployar $component"
        echo ""
    fi
done

# Resumo
echo "=========================================="
echo "RESUMO DO DEPLOYMENT"
echo "=========================================="
echo -e "${BLUE}Total de componentes:${NC} $TOTAL"
echo -e "${GREEN}Sucesso:${NC} $SUCCESS"
echo -e "${RED}Falhas:${NC} $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}=========================================="
    echo "✓ TODOS OS COMPONENTES DEPLOYADOS!"
    echo "==========================================${NC}"
    echo ""
    echo "Próximo passo: Executar teste end-to-end"
    echo "  ./tests/phase1-end-to-end-test.sh --continue-on-error"
    exit 0
else
    echo -e "${YELLOW}=========================================="
    echo "⚠ ALGUNS COMPONENTES FALHARAM"
    echo "==========================================${NC}"
    exit 1
fi
