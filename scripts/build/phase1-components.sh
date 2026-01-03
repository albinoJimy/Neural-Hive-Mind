#!/bin/bash
set -eo pipefail
source "$(dirname "$0")/../lib/common.sh"

# Build Docker images para componentes faltantes da Fase 1
# Uso: ./scripts/build/phase1-components.sh

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Build Componentes Fase 1${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Configuração
IMAGE_TAG="${IMAGE_TAG:-1.0.0}"
USE_MINIKUBE="${USE_MINIKUBE:-auto}"

# Pré-verificações
echo -e "${BLUE}Executando pré-verificações...${NC}"

# Verificar se Docker daemon está rodando
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}✗ Docker daemon não está acessível${NC}"
    echo -e "${YELLOW}Verifique se o Docker está rodando: systemctl status docker${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker daemon acessível${NC}"

# Verificar espaço em disco
DOCKER_ROOT=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo "/var/lib/docker")
AVAILABLE_SPACE_KB=$(df -P "$DOCKER_ROOT" | tail -1 | awk '{print $4}')
AVAILABLE_SPACE_GB=$((AVAILABLE_SPACE_KB / 1024 / 1024))
MINIMUM_SPACE_GB=2

if [ $AVAILABLE_SPACE_GB -lt $MINIMUM_SPACE_GB ]; then
    echo -e "${RED}✗ Espaço em disco insuficiente: ${AVAILABLE_SPACE_GB}GB disponível (mínimo: ${MINIMUM_SPACE_GB}GB)${NC}"
    echo -e "${YELLOW}Sugestão: execute 'docker system prune -a' para liberar espaço${NC}"
    docker system df
    exit 1
fi
echo -e "${GREEN}✓ Espaço em disco suficiente: ${AVAILABLE_SPACE_GB}GB disponível${NC}"
echo ""

# Componentes para build
declare -A COMPONENTS=(
    ["semantic-translation-engine"]="neural-hive-mind/semantic-translation-engine"
    ["consensus-engine"]="neural-hive-mind/consensus-engine"
    ["memory-layer-api"]="neural-hive-mind/memory-layer-api"
    ["worker-agents"]="neural-hive-mind/worker-agents"
    ["specialist-business"]="neural-hive-mind/specialist-business"
)

# Detectar se está usando Minikube
if [ "$USE_MINIKUBE" = "auto" ]; then
    if command -v minikube &> /dev/null && minikube status &> /dev/null; then
        echo -e "${BLUE}ℹ${NC} Minikube detectado e rodando"
        USE_MINIKUBE="yes"
    else
        echo -e "${BLUE}ℹ${NC} Minikube não detectado, usando Docker local"
        USE_MINIKUBE="no"
    fi
fi

# Configurar Docker para Minikube se necessário
if [ "$USE_MINIKUBE" = "yes" ]; then
    echo -e "${YELLOW}Configurando Docker para usar daemon do Minikube...${NC}"
    eval $(minikube docker-env)
    if [ $? -ne 0 ]; then
        echo -e "${RED}✗ Falha ao configurar Minikube Docker environment${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Docker configurado para Minikube${NC}"
    echo ""
fi

# Diretório do projeto
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}Diretório do projeto:${NC} $PROJECT_ROOT"
echo -e "${BLUE}Tag de imagem:${NC} $IMAGE_TAG"
echo ""

# Criar diretório para artefatos de build
BUILD_ARTIFACTS_DIR="$PROJECT_ROOT/build-artifacts"
mkdir -p "$BUILD_ARTIFACTS_DIR"
IMAGES_MANIFEST="$BUILD_ARTIFACTS_DIR/images-${IMAGE_TAG}.jsonl"

# Contadores
SUCCESS_COUNT=0
FAILED_COUNT=0
FAILED_COMPONENTS=()

# Build de cada componente
for component in "${!COMPONENTS[@]}"; do
    IMAGE_REPO="${COMPONENTS[$component]}"
    IMAGE_NAME="${IMAGE_REPO}:${IMAGE_TAG}"
    DOCKERFILE_PATH="services/${component}/Dockerfile"

    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Building: $component${NC}"
    echo -e "${GREEN}========================================${NC}"

    # Verificar se Dockerfile existe
    if [ ! -f "$DOCKERFILE_PATH" ]; then
        echo -e "${RED}✗${NC} Dockerfile não encontrado: $DOCKERFILE_PATH"
        FAILED_COUNT=$((FAILED_COUNT + 1))
        FAILED_COMPONENTS+=("$component (Dockerfile ausente)")
        echo ""
        continue
    fi

    # Verificar se o diretório do serviço existe
    if [ ! -d "services/${component}" ]; then
        echo -e "${RED}✗${NC} Diretório do serviço não encontrado: services/${component}"
        FAILED_COUNT=$((FAILED_COUNT + 1))
        FAILED_COMPONENTS+=("$component (diretório ausente)")
        echo ""
        continue
    fi

    # Timer
    START_TIME=$(date +%s)

    # Build da imagem
    echo -e "${YELLOW}Imagem:${NC} $IMAGE_NAME"
    echo -e "${YELLOW}Dockerfile:${NC} $DOCKERFILE_PATH"
    echo -e "${YELLOW}Contexto:${NC} $PROJECT_ROOT"
    echo ""

    if docker build -t "$IMAGE_NAME" -f "$DOCKERFILE_PATH" . 2>&1 | tee "/tmp/build-${component}.log"; then
        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))
        echo ""
        echo -e "${GREEN}✓ Build concluído com sucesso: $IMAGE_NAME (${DURATION}s)${NC}"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))

        # Verificar e inspecionar a imagem criada
        if docker image inspect "$IMAGE_REPO:$IMAGE_TAG" >/dev/null 2>&1; then
            # Extrair informações detalhadas da imagem
            IMAGE_ID=$(docker image inspect "$IMAGE_REPO:$IMAGE_TAG" --format '{{.Id}}')
            IMAGE_SIZE=$(docker image inspect "$IMAGE_REPO:$IMAGE_TAG" --format '{{.Size}}')
            IMAGE_SIZE_HUMAN=$(docker images "$IMAGE_REPO:$IMAGE_TAG" --format "{{.Size}}")
            IMAGE_CREATED=$(docker image inspect "$IMAGE_REPO:$IMAGE_TAG" --format '{{.Created}}')
            IMAGE_DIGEST=$(docker images --digests "$IMAGE_REPO:$IMAGE_TAG" --format "{{.Digest}}" | head -1)

            echo -e "${GREEN}✓ Imagem criada e verificada: $IMAGE_SIZE_HUMAN${NC}"

            # Gravar informações no manifest JSONL
            cat >> "$IMAGES_MANIFEST" <<EOF
{"component":"$component","repository":"$IMAGE_REPO","tag":"$IMAGE_TAG","id":"$IMAGE_ID","size":$IMAGE_SIZE,"size_human":"$IMAGE_SIZE_HUMAN","created":"$IMAGE_CREATED","digest":"$IMAGE_DIGEST","build_duration":$DURATION}
EOF
        else
            echo -e "${YELLOW}⚠ Aviso: Imagem construída mas não encontrada na inspeção${NC}"
        fi
    else
        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))
        echo ""
        echo -e "${RED}✗ Falha no build: $IMAGE_NAME (${DURATION}s)${NC}"
        echo -e "${RED}Ver logs em: /tmp/build-${component}.log${NC}"
        FAILED_COUNT=$((FAILED_COUNT + 1))
        FAILED_COMPONENTS+=("$component (build falhou)")
    fi

    echo ""
done

# Resumo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}RESUMO DO BUILD${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Total:${NC} ${#COMPONENTS[@]} componentes"
echo -e "${GREEN}Sucesso:${NC} $SUCCESS_COUNT"
echo -e "${RED}Falhas:${NC} $FAILED_COUNT"
echo ""

if [ $FAILED_COUNT -gt 0 ]; then
    echo -e "${RED}Componentes com falha:${NC}"
    for failed in "${FAILED_COMPONENTS[@]}"; do
        echo -e "${RED}  - $failed${NC}"
    done
    echo ""
fi

# Listar imagens criadas com digest
echo -e "${YELLOW}Imagens criadas:${NC}"
for component in "${!COMPONENTS[@]}"; do
    IMAGE_REPO="${COMPONENTS[$component]}"
    if docker image inspect "$IMAGE_REPO:$IMAGE_TAG" >/dev/null 2>&1; then
        IMAGE_SIZE=$(docker images "$IMAGE_REPO:$IMAGE_TAG" --format "{{.Size}}")
        IMAGE_DIGEST=$(docker images --digests "$IMAGE_REPO:$IMAGE_TAG" --format "{{.Digest}}" | head -1)
        if [ -n "$IMAGE_DIGEST" ] && [ "$IMAGE_DIGEST" != "<none>" ]; then
            echo -e "  ✓ $IMAGE_REPO:$IMAGE_TAG ($IMAGE_SIZE) digest: $IMAGE_DIGEST"
        else
            echo -e "  ✓ $IMAGE_REPO:$IMAGE_TAG ($IMAGE_SIZE)"
        fi
    fi
done
echo ""
echo -e "${BLUE}Manifest de imagens salvo em:${NC} $IMAGES_MANIFEST"
echo ""

# Status final
if [ $FAILED_COUNT -gt 0 ]; then
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ Build completado com erros${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
else
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ TODAS AS IMAGENS CONSTRUÍDAS!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${BLUE}Próximo passo:${NC}"
    echo -e "  ./deploy-fase1-componentes-faltantes.sh"
    exit 0
fi
