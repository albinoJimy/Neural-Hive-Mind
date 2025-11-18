#!/bin/bash
# Script para build e push de imagens Docker para ECR
# Neural Hive-Mind - Version 1.0

set -euo pipefail

# Cores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Carregar variáveis de ambiente
if [ -f ~/.neural-hive-dev-env ]; then
    source ~/.neural-hive-dev-env
else
    log_error "Arquivo de ambiente não encontrado: ~/.neural-hive-dev-env"
    exit 1
fi

log_info "============================================"
log_info "Build e Push de Imagens Docker para ECR"
log_info "============================================"
log_info "Ambiente: ${ENV}"
log_info "ECR Registry: ${ECR_REGISTRY}"
log_info ""

# Login no ECR
log_info "Fazendo login no ECR..."
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin ${ECR_REGISTRY}

if [ $? -ne 0 ]; then
    log_error "Falha ao fazer login no ECR"
    exit 1
fi
log_success "Login no ECR bem-sucedido"

cd /jimy/Neural-Hive-Mind

# Lista de imagens para build
declare -A IMAGES
IMAGES["gateway-intencoes"]="services/gateway-intencoes/Dockerfile"
IMAGES["semantic-translation-engine"]="services/semantic-translation-engine/Dockerfile"
IMAGES["consensus-engine"]="services/consensus-engine/Dockerfile"
IMAGES["memory-layer-api"]="services/memory-layer-api/Dockerfile"

# Specialists (usam o mesmo Dockerfile base)
SPECIALISTS=("business" "technical" "behavior" "evolution" "architecture")

# Build e push das imagens principais
log_info "Building e pushing imagens principais..."
for name in "${!IMAGES[@]}"; do
    dockerfile="${IMAGES[$name]}"

    if [ ! -f "$dockerfile" ]; then
        log_warning "Dockerfile não encontrado: $dockerfile, pulando..."
        continue
    fi

    image_tag="${ECR_REGISTRY}/${ENV}/${name}:latest"

    log_info "Building ${name}..."
    docker build -t "$image_tag" -f "$dockerfile" . || {
        log_error "Falha ao buildar ${name}"
        continue
    }

    log_info "Pushing ${name}..."
    docker push "$image_tag" || {
        log_error "Falha ao push ${name}"
        continue
    }

    log_success "✅ ${name} completo"
done

# Build e push dos specialists
log_info "Building e pushing specialists..."
for spec in "${SPECIALISTS[@]}"; do
    dockerfile="services/specialist-${spec}/Dockerfile"

    if [ ! -f "$dockerfile" ]; then
        log_warning "Dockerfile não encontrado: $dockerfile, pulando..."
        continue
    fi

    image_tag="${ECR_REGISTRY}/${ENV}/specialist-${spec}:latest"

    log_info "Building specialist-${spec}..."
    docker build -t "$image_tag" -f "$dockerfile" . || {
        log_error "Falha ao buildar specialist-${spec}"
        continue
    }

    log_info "Pushing specialist-${spec}..."
    docker push "$image_tag" || {
        log_error "Falha ao push specialist-${spec}"
        continue
    }

    log_success "✅ specialist-${spec} completo"
done

log_success "============================================"
log_success "Build e push de imagens concluído!"
log_success "============================================"
log_info ""
log_info "Verificar imagens no ECR:"
log_info "  aws ecr list-images --repository-name ${ENV}/gateway-intencoes --region ${AWS_REGION}"
log_info ""
log_info "Próximo passo:"
log_info "  Deploy dos componentes Kubernetes"
