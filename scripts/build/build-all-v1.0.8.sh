#!/bin/bash
set -euo pipefail

# Build Docker images v1.0.8 com correção de timestamp
# Uso: ./scripts/build/build-all-v1.0.8.sh

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Build v1.0.8 - Timestamp Fix${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Configuração
VERSION="1.0.8"
REGISTRY="${REGISTRY:-neural-hive-mind}"

# Diretório do projeto
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}Diretório do projeto:${NC} $PROJECT_ROOT"
echo -e "${BLUE}Versão:${NC} $VERSION"
echo -e "${BLUE}Registry:${NC} $REGISTRY"
echo ""

# Componentes para build
COMPONENTS=(
    "specialist-business"
    "specialist-technical"
    "specialist-behavior"
    "specialist-evolution"
    "specialist-architecture"
    "consensus-engine"
)

# Contadores
SUCCESS_COUNT=0
FAILED_COUNT=0
FAILED_COMPONENTS=()

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}FASE 1: Build da Biblioteca${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Build da biblioteca neural_hive_specialists
LIB_DIR="$PROJECT_ROOT/libraries/python/neural_hive_specialists"
if [ -d "$LIB_DIR" ]; then
    echo -e "${YELLOW}Buildando biblioteca neural_hive_specialists v${VERSION}...${NC}"
    cd "$LIB_DIR"

    # Criar wheel
    if command -v poetry &> /dev/null; then
        echo "Usando Poetry para build..."
        poetry build
    elif [ -f "setup.py" ]; then
        echo "Usando setup.py para build..."
        python3 setup.py sdist bdist_wheel
    else
        echo -e "${RED}✗ Nem Poetry nem setup.py encontrado${NC}"
        exit 1
    fi

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Biblioteca neural_hive_specialists v${VERSION} buildada${NC}"
        # Copiar wheel para onde os Dockerfiles podem acessar
        mkdir -p "$PROJECT_ROOT/dist"
        cp -f dist/*.whl "$PROJECT_ROOT/dist/" 2>/dev/null || true
    else
        echo -e "${RED}✗ Falha ao buildar biblioteca${NC}"
        exit 1
    fi

    cd "$PROJECT_ROOT"
    echo ""
else
    echo -e "${YELLOW}⚠ Biblioteca não encontrada, pulando...${NC}"
    echo ""
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}FASE 2: Build das Imagens Docker${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Build de cada componente
for component in "${COMPONENTS[@]}"; do
    IMAGE_NAME="${REGISTRY}/${component}:${VERSION}"
    DOCKERFILE_PATH="services/${component}/Dockerfile"

    echo -e "${GREEN}----------------------------------------${NC}"
    echo -e "${GREEN}Building: $component${NC}"
    echo -e "${GREEN}----------------------------------------${NC}"

    # Verificar se Dockerfile existe
    if [ ! -f "$DOCKERFILE_PATH" ]; then
        echo -e "${RED}✗ Dockerfile não encontrado: $DOCKERFILE_PATH${NC}"
        FAILED_COUNT=$((FAILED_COUNT + 1))
        FAILED_COMPONENTS+=("$component (Dockerfile ausente)")
        echo ""
        continue
    fi

    # Timer
    START_TIME=$(date +%s)

    # Build da imagem
    echo -e "${YELLOW}Imagem:${NC} $IMAGE_NAME"
    echo -e "${YELLOW}Dockerfile:${NC} $DOCKERFILE_PATH"
    echo ""

    docker build \
        -t "$IMAGE_NAME" \
        -t "${REGISTRY}/${component}:latest" \
        -f "$DOCKERFILE_PATH" \
        --build-arg VERSION="$VERSION" \
        .

    if [ $? -eq 0 ]; then
        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))
        echo -e "${GREEN}✓ Build completo: $component (${DURATION}s)${NC}"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))

        # Verificar se imagem foi criada
        if docker images | grep -q "$IMAGE_NAME"; then
            IMAGE_SIZE=$(docker images "$IMAGE_NAME" --format "{{.Size}}")
            echo -e "${BLUE}  Tamanho da imagem: $IMAGE_SIZE${NC}"
        fi
    else
        echo -e "${RED}✗ Falha no build: $component${NC}"
        FAILED_COUNT=$((FAILED_COUNT + 1))
        FAILED_COMPONENTS+=("$component")
    fi

    echo ""
done

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}RESUMO DO BUILD${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${GREEN}Sucesso:${NC} $SUCCESS_COUNT/${#COMPONENTS[@]}"
echo -e "${RED}Falhas:${NC} $FAILED_COUNT/${#COMPONENTS[@]}"
echo ""

if [ $FAILED_COUNT -gt 0 ]; then
    echo -e "${RED}Componentes com falha:${NC}"
    for failed in "${FAILED_COMPONENTS[@]}"; do
        echo -e "  ${RED}✗${NC} $failed"
    done
    echo ""
fi

echo -e "${BLUE}Imagens buildadas:${NC}"
for component in "${COMPONENTS[@]}"; do
    if docker images | grep -q "${REGISTRY}/${component}.*${VERSION}"; then
        echo -e "  ${GREEN}✓${NC} ${REGISTRY}/${component}:${VERSION}"
    fi
done
echo ""

if [ $FAILED_COUNT -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ BUILD COMPLETO v${VERSION}${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${YELLOW}Próximo passo:${NC}"
    echo -e "  ./scripts/deploy/deploy-all-v1.0.8.sh"
    echo ""
    exit 0
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ BUILD FALHOU${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    exit 1
fi
