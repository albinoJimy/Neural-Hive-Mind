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
# Script para Build Completo dos Serviços (Fase 1 + Fase 2)
# Executa build das imagens base + todos os 19 serviços do Neural Hive-Mind
# Fase 1: 7 serviços (consensus-engine, 5 specialists, optimizer-agents)
# Fase 2: 12 serviços (orchestrator-dynamic, queen-agent, worker-agents, etc.)
# =============================================================================

set -e

REGISTRY="37.60.241.150:30500"
TAG="${TAG:-1.0.0}"  # Default: 1.0.0 (release), pode ser sobrescrito via TAG=latest ./script.sh

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_header() {
    echo ""
    echo "============================================================================="
    echo -e "${BLUE}$1${NC}"
    echo "============================================================================="
}

# Verificar se estamos no diretório correto
if [ ! -f "scripts/build-base-images.sh" ]; then
    log_error "Execute este script do diretório raiz do projeto Neural-Hive-Mind"
    exit 1
fi

# =============================================================================
# FASE 1: Build das Imagens Base (Fase 1 + Fase 2)
# =============================================================================
log_header "FASE 1: BUILD DAS IMAGENS BASE (Fase 1 + Fase 2)"

log_info "Construindo imagens base (python-ml-base, python-grpc-base, etc)..."
log_info "Este processo pode demorar 10-15 minutos na primeira execução..."

./scripts/build-base-images.sh

log_success "Imagens base construídas com sucesso!"

# =============================================================================
# FASE 2: Build dos Serviços (Fase 1 + Fase 2)
# =============================================================================
log_header "FASE 2: BUILD DOS SERVIÇOS (Fase 1 + Fase 2)"

# Serviços da Fase 1 (ML otimizado) + Fase 2 (Camada de Execução completa)
# Fase 1:
# - consensus-engine: removido neural_hive_specialists, usa python-grpc-base
# - specialists: removido pm4py, prophet, pulp, statsmodels
# - optimizer-agents: consolidado Prophet/statsmodels aqui
# Fase 2:
# - orchestrator-dynamic, queen-agent, worker-agents, code-forge
# - service-registry, execution-ticket-service, scout-agents
# - analyst-agents, guard-agents, sla-management-system
# - mcp-tool-catalog, self-healing-engine
SERVICES=(
    # Fase 1 (existentes)
    "consensus-engine"
    "specialist-business"
    "specialist-technical"
    "specialist-architecture"
    "specialist-behavior"
    "specialist-evolution"
    "optimizer-agents"

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
    log_info "[$CURRENT/$TOTAL] Construindo $SERVICE..."

    if ./scripts/build-and-push-to-registry.sh build "$SERVICE" "$TAG"; then
        log_success "$SERVICE construído com sucesso!"
    else
        log_error "Falha ao construir $SERVICE"
        FAILED+=("$SERVICE")
    fi
done

# =============================================================================
# RESUMO FINAL
# =============================================================================
log_header "RESUMO DO BUILD"

echo ""
echo "Total de serviços: $TOTAL"
echo "Sucesso: $((TOTAL - ${#FAILED[@]}))"
echo "Falhas: ${#FAILED[@]}"

if [ ${#FAILED[@]} -gt 0 ]; then
    log_error "Serviços que falharam:"
    for SERVICE in "${FAILED[@]}"; do
        echo "  - $SERVICE"
    done
    exit 1
else
    log_success "Todos os serviços foram construídos com sucesso!"
    echo ""
    log_info "Para aplicar as mudanças no cluster, execute:"
    echo ""
    echo "  kubectl rollout restart deployment -n neural-hive --all"
    echo ""
fi
