#!/bin/bash
set -eo pipefail
source "$(dirname "$0")/../lib/common.sh"

# Script para importar imagens Docker no containerd do Kubernetes
# Executa no próprio node do cluster

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Importar Imagens no Containerd${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Configuração
IMAGE_TAG="${IMAGE_TAG:-1.0.0}"

# Imagens para importar
IMAGES=(
    "neural-hive-mind/semantic-translation-engine:${IMAGE_TAG}"
    "neural-hive-mind/memory-layer-api:${IMAGE_TAG}"
    "neural-hive-mind/consensus-engine:${IMAGE_TAG}"
    "neural-hive-mind/worker-agents:${IMAGE_TAG}"
    "neural-hive-mind/specialist-business:${IMAGE_TAG}"
)

TEMP_DIR="/tmp/neural-hive-images"
mkdir -p "$TEMP_DIR"

SUCCESS=0
FAILED=0

for image in "${IMAGES[@]}"; do
    name=$(echo "$image" | cut -d/ -f2 | cut -d: -f1)
    tarfile="$TEMP_DIR/${name}.tar"

    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}Processando: $image${NC}"
    echo -e "${BLUE}========================================${NC}"

    # Verificar se imagem existe no Docker
    if ! docker image inspect "$image" >/dev/null 2>&1; then
        echo -e "${RED}✗${NC} Imagem não encontrada no Docker: $image"
        echo "Execute o build primeiro"
        ((FAILED++))
        echo ""
        continue
    fi

    echo -e "${YELLOW}1. Salvando imagem do Docker...${NC}"
    if docker save "$image" -o "$tarfile"; then
        SIZE=$(du -h "$tarfile" | cut -f1)
        echo -e "${GREEN}✓${NC} Salvo: $SIZE em $tarfile"
    else
        echo -e "${RED}✗${NC} Falha ao salvar"
        ((FAILED++))
        continue
    fi

    echo -e "${YELLOW}2. Importando no containerd (namespace k8s.io)...${NC}"
    if ctr -n k8s.io images import "$tarfile" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Importado com sucesso"
        ((SUCCESS++))
    else
        echo -e "${YELLOW}Tentando com sudo...${NC}"
        if sudo ctr -n k8s.io images import "$tarfile"; then
            echo -e "${GREEN}✓${NC} Importado com sudo"
            ((SUCCESS++))
        else
            echo -e "${RED}✗${NC} Falha ao importar"
            ((FAILED++))
        fi
    fi

    # Remover tar após importar
    rm -f "$tarfile"
    echo ""
done

# Limpar diretório temporário
rm -rf "$TEMP_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Verificando imagens no containerd...${NC}"
echo -e "${BLUE}========================================${NC}"

for image in "${IMAGES[@]}"; do
    repo=$(echo "$image" | cut -d: -f1)
    echo -e "${YELLOW}Verificando${NC} $image..."

    if ctr -n k8s.io images ls | grep -q "$repo"; then
        echo -e "${GREEN}✓${NC} Disponível no containerd"
    else
        if sudo ctr -n k8s.io images ls | grep -q "$repo"; then
            echo -e "${GREEN}✓${NC} Disponível no containerd (verificado com sudo)"
        else
            echo -e "${RED}✗${NC} NÃO encontrada"
        fi
    fi
done
echo ""

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}RESUMO${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Sucesso:${NC} $SUCCESS"
echo -e "${RED}Falhas:${NC} $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ TODAS AS IMAGENS IMPORTADAS!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${BLUE}Próximos passos:${NC}"
    echo "  1. Atualizar Helm values: imagePullPolicy: Never"
    echo "  2. Verificar que repository names nos Helm charts correspondem às imagens importadas"
    echo "  3. Deploy: ./deploy-fase1-componentes-faltantes.sh"
    exit 0
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ ALGUMAS IMAGENS FALHARAM${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
