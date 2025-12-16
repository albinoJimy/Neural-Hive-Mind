#!/bin/bash
# ============================================================================
# ⚠️  DEPRECATION WARNING
# ============================================================================
# Este script está deprecated e será removido em versão futura.
# Use o novo CLI unificado: ./scripts/build.sh
#
# Equivalência:
#   ./scripts/build-local-parallel.sh --version 1.0.8
#   → ./scripts/build.sh --target local --version 1.0.8
#
#   ./scripts/push-to-ecr.sh --version 1.0.8
#   → ./scripts/build.sh --target ecr --version 1.0.8
# ============================================================================

echo ""
echo "⚠️  AVISO: Este script está deprecated"
echo "   Use: ./scripts/build.sh --target <local|ecr|registry|all>"
echo "   Documentação: ./scripts/build.sh --help"
echo ""
sleep 2

# =============================================================================
# Script para Rebuild Completo: Base Images + Services (Fase 1 + Fase 2)
# Executa na ordem correta de dependências
#
# Este script é um alias/wrapper para build-all-optimized-services.sh
# Para rebuild completo de todos os 19 serviços (Fase 1 + Fase 2), use:
#   ./scripts/build-all-optimized-services.sh
#
# Este script mantém compatibilidade legada e também executa todos os serviços.
# =============================================================================

set -e

REGISTRY="37.60.241.150:30500"
TAG="${TAG:-1.0.0}"  # Default: 1.0.0 (release), pode ser sobrescrito via TAG=latest ./script.sh
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_header() {
    echo ""
    echo "============================================================================="
    echo -e "${BLUE}$1${NC}"
    echo "============================================================================="
}

cd "$PROJECT_ROOT"

# =============================================================================
# FASE 1: Build das Imagens Base (ordem de dependências)
# =============================================================================
log_header "FASE 1: BUILD DAS IMAGENS BASE"

# Ordem correta de dependências:
# python-ml-base -> python-grpc-base -> python-mlops-base
#                                    -> python-nlp-base -> python-specialist-base

BASE_IMAGES=(
    "python-ml-base"
    "python-grpc-base"
    "python-mlops-base"
    "python-nlp-base"
    "python-specialist-base"
)

for img in "${BASE_IMAGES[@]}"; do
    log_info "Building $img..."
    if [ -f "base-images/$img/Dockerfile" ]; then
        docker build \
            -t "neural-hive-mind/${img}:1.0.0" \
            -t "neural-hive-mind/${img}:latest" \
            -f "base-images/${img}/Dockerfile" \
            . || { log_error "Failed to build $img"; exit 1; }
        log_success "$img built!"
    else
        log_error "Dockerfile not found: base-images/$img/Dockerfile"
        exit 1
    fi
done

log_success "All base images built!"

# Verificar imagens base
log_info "Verificando imagens base..."
docker images | grep neural-hive-mind

# =============================================================================
# FASE 2: Build e Push dos Services
# =============================================================================
log_header "FASE 2: BUILD E PUSH DOS SERVICES"

SERVICES=(
    # Fase 1 (existentes)
    "consensus-engine"
    "specialist-business"
    "specialist-technical"
    "specialist-architecture"
    "specialist-behavior"
    "specialist-evolution"
    "optimizer-agents"
    "semantic-translation-engine"

    # Fase 2 (novos)
    "orchestrator-dynamic"
    "queen-agent"
    "worker-agents"
    "code-forge"
    "service-registry"
    "execution-ticket-service"
    "scout-agents"
    "analyst-agents"
    "guard-agents"
    "sla-management-system"
    "mcp-tool-catalog"
    "self-healing-engine"
)

TOTAL=${#SERVICES[@]}
CURRENT=0
FAILED=()

for SERVICE in "${SERVICES[@]}"; do
    CURRENT=$((CURRENT + 1))
    log_info "[$CURRENT/$TOTAL] Building and pushing $SERVICE..."

    if ./scripts/build-and-push-to-registry.sh build "$SERVICE" "$TAG"; then
        log_success "$SERVICE done!"
    else
        log_error "Failed: $SERVICE"
        FAILED+=("$SERVICE")
    fi
done

# =============================================================================
# RESUMO
# =============================================================================
log_header "RESUMO"

echo "Total services: $TOTAL"
echo "Success: $((TOTAL - ${#FAILED[@]}))"
echo "Failed: ${#FAILED[@]}"

if [ ${#FAILED[@]} -gt 0 ]; then
    log_error "Failed services:"
    for s in "${FAILED[@]}"; do
        echo "  - $s"
    done
    exit 1
else
    log_success "All services built and pushed!"
fi

# Verificar no registry
log_header "VERIFICANDO REGISTRY"
curl -s "http://${REGISTRY}/v2/_catalog" | jq .
