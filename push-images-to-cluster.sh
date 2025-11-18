#!/bin/bash
set -eo pipefail

# Script para enviar imagens Docker para o cluster Kubernetes com containerd
# Uso: ./push-images-to-cluster.sh

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Push de Imagens para Cluster${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Configuração
IMAGE_TAG="${IMAGE_TAG:-1.0.0}"
NODE_HOST="vmi2092350.contaboserver.net"
NODE_USER="root"  # Ajustar se necessário
TEMP_DIR="/tmp/neural-hive-images"

# Imagens para transferir
declare -A IMAGES=(
    ["semantic-translation-engine"]="neural-hive-mind/semantic-translation-engine:${IMAGE_TAG}"
    ["memory-layer-api"]="neural-hive-mind/memory-layer-api:${IMAGE_TAG}"
    ["consensus-engine"]="neural-hive-mind/consensus-engine:${IMAGE_TAG}"
    ["worker-agents"]="neural-hive-mind/worker-agents:${IMAGE_TAG}"
    ["specialist-business"]="neural-hive-mind/specialist-business:${IMAGE_TAG}"
)

# Verificar se imagens existem localmente
echo -e "${BLUE}Verificando imagens locais...${NC}"
for name in "${!IMAGES[@]}"; do
    image="${IMAGES[$name]}"
    if docker image inspect "$image" >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $image encontrada"
    else
        echo -e "${RED}✗${NC} $image NÃO encontrada"
        echo "Execute o build primeiro: ./build-fase1-componentes.sh"
        exit 1
    fi
done
echo ""

# Criar diretório temporário local
mkdir -p "$TEMP_DIR"
cd "$TEMP_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Salvando imagens em arquivos tar...${NC}"
echo -e "${BLUE}========================================${NC}"

for name in "${!IMAGES[@]}"; do
    image="${IMAGES[$name]}"
    tarfile="${name}.tar"

    echo -e "${YELLOW}Salvando${NC} $image -> $tarfile"

    if docker save "$image" -o "$tarfile"; then
        SIZE=$(du -h "$tarfile" | cut -f1)
        echo -e "${GREEN}✓${NC} Salvo: $SIZE"
    else
        echo -e "${RED}✗${NC} Falha ao salvar $image"
        exit 1
    fi
    echo ""
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Copiando imagens para o cluster...${NC}"
echo -e "${BLUE}========================================${NC}"

# Criar diretório no node remoto
echo -e "${YELLOW}Criando diretório no node...${NC}"
ssh "${NODE_USER}@${NODE_HOST}" "mkdir -p /tmp/neural-hive-images" || {
    echo -e "${RED}✗${NC} Falha ao criar diretório remoto"
    echo "Verifique conectividade SSH: ssh ${NODE_USER}@${NODE_HOST}"
    exit 1
}

# Copiar cada imagem
for name in "${!IMAGES[@]}"; do
    tarfile="${name}.tar"

    echo -e "${YELLOW}Copiando${NC} $tarfile para $NODE_HOST..."

    if scp "$tarfile" "${NODE_USER}@${NODE_HOST}:/tmp/neural-hive-images/"; then
        echo -e "${GREEN}✓${NC} Copiado com sucesso"
    else
        echo -e "${RED}✗${NC} Falha ao copiar $tarfile"
        exit 1
    fi
done
echo ""

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Importando imagens no containerd...${NC}"
echo -e "${BLUE}========================================${NC}"

for name in "${!IMAGES[@]}"; do
    image="${IMAGES[$name]}"
    tarfile="/tmp/neural-hive-images/${name}.tar"

    echo -e "${YELLOW}Importando${NC} $image no containerd..."

    # Importar no containerd do Kubernetes (namespace k8s.io)
    if ssh "${NODE_USER}@${NODE_HOST}" "ctr -n k8s.io images import $tarfile"; then
        echo -e "${GREEN}✓${NC} Importado com sucesso"
    else
        echo -e "${RED}✗${NC} Falha ao importar $image"
        echo "Tentando com sudo..."
        if ssh "${NODE_USER}@${NODE_HOST}" "sudo ctr -n k8s.io images import $tarfile"; then
            echo -e "${GREEN}✓${NC} Importado com sudo"
        else
            echo -e "${RED}✗${NC} Falha mesmo com sudo"
        fi
    fi
done
echo ""

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Verificando imagens no cluster...${NC}"
echo -e "${BLUE}========================================${NC}"

for name in "${!IMAGES[@]}"; do
    image="${IMAGES[$name]}"

    echo -e "${YELLOW}Verificando${NC} $image..."

    if ssh "${NODE_USER}@${NODE_HOST}" "ctr -n k8s.io images ls | grep $(echo $image | cut -d: -f1)"; then
        echo -e "${GREEN}✓${NC} Imagem disponível no cluster"
    else
        echo -e "${RED}✗${NC} Imagem NÃO encontrada"
    fi
done
echo ""

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Limpando arquivos temporários...${NC}"
echo -e "${BLUE}========================================${NC}"

# Limpar localmente
cd /
rm -rf "$TEMP_DIR"
echo -e "${GREEN}✓${NC} Arquivos locais removidos"

# Limpar remotamente
ssh "${NODE_USER}@${NODE_HOST}" "rm -rf /tmp/neural-hive-images"
echo -e "${GREEN}✓${NC} Arquivos remotos removidos"
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ IMAGENS TRANSFERIDAS COM SUCESSO!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Próximo passo:${NC}"
echo "  1. Atualizar Helm values com imagePullPolicy: Never"
echo "  2. Re-deploy: ./deploy-fase1-componentes-faltantes.sh"
echo ""
