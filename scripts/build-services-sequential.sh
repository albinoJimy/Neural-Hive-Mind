#!/bin/bash
# =============================================================================
# Neural Hive-Mind - Build Sequencial de Serviços
# =============================================================================
# Executa o build e push de cada serviço na ordem de dependências
# Ordem: Base images -> Serviços independentes -> Serviços dependentes
# =============================================================================

set -e

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configurações
REGISTRY="37.60.241.150:30500"
PROJECT_DIR="/jimy/Neural-Hive-Mind"

# Ordem de build baseada em dependências
# Grupo 1: Base images (se necessário)
BASE_IMAGES=(
    "python-ml-base"
    "python-grpc-base"
    "python-mlops-base"
    "python-nlp-base"
    "python-specialist-base"
)

# Grupo 2: Serviços core (sem dependências internas)
CORE_SERVICES=(
    "service-registry"
    "gateway-intencoes"
    "consensus-engine"
    "semantic-translation-engine"
)

# Grupo 3: Specialists (dependem de python-specialist-base)
SPECIALIST_SERVICES=(
    "specialist-business"
    "specialist-technical"
    "specialist-behavior"
    "specialist-evolution"
    "specialist-architecture"
)

# Grupo 4: Agentes (podem depender de core services)
AGENT_SERVICES=(
    "scout-agents"
    "worker-agents"
    "guard-agents"
    "analyst-agents"
    "optimizer-agents"
    "queen-agent"
)

# Grupo 5: Serviços de suporte
SUPPORT_SERVICES=(
    "mcp-tool-catalog"
    "code-forge"
    "execution-ticket-service"
    "self-healing-engine"
    "sla-management-system"
    "orchestrator-dynamic"
    "memory-layer-api"
    "explainability-api"
)

# Contadores
TOTAL=0
SUCCESS=0
FAILED=0
SKIPPED=0

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[FAIL]${NC} $1"; }
log_header() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════════${NC}"
}

build_and_push() {
    local service=$1
    local dockerfile="${PROJECT_DIR}/services/${service}/Dockerfile"
    local image="${REGISTRY}/${service}:latest"

    ((TOTAL++))

    echo ""
    echo -e "${YELLOW}────────────────────────────────────────────────────────────────────${NC}"
    echo -e "${YELLOW}[${TOTAL}] Building: ${service}${NC}"
    echo -e "${YELLOW}────────────────────────────────────────────────────────────────────${NC}"

    if [ ! -f "$dockerfile" ]; then
        log_warn "Dockerfile não encontrado: $dockerfile"
        ((SKIPPED++))
        return 1
    fi

    cd "$PROJECT_DIR"

    # Build
    log_info "Docker build..."
    if DOCKER_BUILDKIT=1 docker build -f "$dockerfile" -t "$image" . 2>&1 | tail -30; then
        log_success "Build concluído: $service"
    else
        log_error "Build falhou: $service"
        ((FAILED++))
        return 1
    fi

    # Push
    log_info "Docker push..."
    if docker push "$image" 2>&1 | tail -10; then
        log_success "Push concluído: $service"
        ((SUCCESS++))
        return 0
    else
        log_error "Push falhou: $service"
        ((FAILED++))
        return 1
    fi
}

build_group() {
    local group_name=$1
    shift
    local services=("$@")

    log_header "$group_name (${#services[@]} serviços)"

    for service in "${services[@]}"; do
        build_and_push "$service" || true
    done
}

show_summary() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  RESUMO FINAL${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  Total processado: ${TOTAL}"
    echo -e "  ${GREEN}Sucesso: ${SUCCESS}${NC}"
    echo -e "  ${RED}Falhou: ${FAILED}${NC}"
    echo -e "  ${YELLOW}Pulado: ${SKIPPED}${NC}"
    echo ""

    # Mostrar imagens no registry
    log_info "Imagens no registry:"
    curl -s http://${REGISTRY}/v2/_catalog | jq -r '.repositories[]' 2>/dev/null | sort | while read img; do
        echo "    - $img"
    done
}

# Menu principal
show_menu() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  Neural Hive-Mind - Build Sequencial${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  1) Build TODOS os serviços (ordem de dependências)"
    echo "  2) Build apenas Core Services"
    echo "  3) Build apenas Specialists"
    echo "  4) Build apenas Agents"
    echo "  5) Build apenas Support Services"
    echo "  6) Build serviço específico"
    echo "  7) Listar imagens no registry"
    echo "  8) Sair"
    echo ""
}

main() {
    while true; do
        show_menu
        read -p "Escolha uma opção: " opt

        case $opt in
            1)
                build_group "CORE SERVICES" "${CORE_SERVICES[@]}"
                build_group "SPECIALIST SERVICES" "${SPECIALIST_SERVICES[@]}"
                build_group "AGENT SERVICES" "${AGENT_SERVICES[@]}"
                build_group "SUPPORT SERVICES" "${SUPPORT_SERVICES[@]}"
                show_summary
                ;;
            2)
                build_group "CORE SERVICES" "${CORE_SERVICES[@]}"
                show_summary
                ;;
            3)
                build_group "SPECIALIST SERVICES" "${SPECIALIST_SERVICES[@]}"
                show_summary
                ;;
            4)
                build_group "AGENT SERVICES" "${AGENT_SERVICES[@]}"
                show_summary
                ;;
            5)
                build_group "SUPPORT SERVICES" "${SUPPORT_SERVICES[@]}"
                show_summary
                ;;
            6)
                echo ""
                echo "Serviços disponíveis:"
                ALL_SERVICES=("${CORE_SERVICES[@]}" "${SPECIALIST_SERVICES[@]}" "${AGENT_SERVICES[@]}" "${SUPPORT_SERVICES[@]}")
                for i in "${!ALL_SERVICES[@]}"; do
                    echo "  $((i+1))) ${ALL_SERVICES[$i]}"
                done
                echo ""
                read -p "Número do serviço: " num
                if [[ "$num" =~ ^[0-9]+$ ]] && [ "$num" -ge 1 ] && [ "$num" -le "${#ALL_SERVICES[@]}" ]; then
                    build_and_push "${ALL_SERVICES[$((num-1))]}"
                else
                    log_error "Seleção inválida"
                fi
                ;;
            7)
                log_info "Imagens no registry ${REGISTRY}:"
                curl -s http://${REGISTRY}/v2/_catalog | jq -r '.repositories[]' 2>/dev/null | sort | while read img; do
                    echo "    - $img"
                done
                ;;
            8)
                log_info "Saindo..."
                exit 0
                ;;
            *)
                log_error "Opção inválida"
                ;;
        esac
    done
}

# Argumentos de linha de comando
case "${1:-}" in
    --all)
        build_group "CORE SERVICES" "${CORE_SERVICES[@]}"
        build_group "SPECIALIST SERVICES" "${SPECIALIST_SERVICES[@]}"
        build_group "AGENT SERVICES" "${AGENT_SERVICES[@]}"
        build_group "SUPPORT SERVICES" "${SUPPORT_SERVICES[@]}"
        show_summary
        ;;
    --core)
        build_group "CORE SERVICES" "${CORE_SERVICES[@]}"
        show_summary
        ;;
    --specialists)
        build_group "SPECIALIST SERVICES" "${SPECIALIST_SERVICES[@]}"
        show_summary
        ;;
    --agents)
        build_group "AGENT SERVICES" "${AGENT_SERVICES[@]}"
        show_summary
        ;;
    --support)
        build_group "SUPPORT SERVICES" "${SUPPORT_SERVICES[@]}"
        show_summary
        ;;
    --service)
        if [ -n "$2" ]; then
            build_and_push "$2"
        else
            log_error "Especifique o nome do serviço"
        fi
        ;;
    --list)
        log_info "Imagens no registry ${REGISTRY}:"
        curl -s http://${REGISTRY}/v2/_catalog | jq -r '.repositories[]' 2>/dev/null | sort
        ;;
    --help|-h)
        echo "Uso: $0 [opção]"
        echo ""
        echo "Opções:"
        echo "  --all          Build todos os serviços"
        echo "  --core         Build core services"
        echo "  --specialists  Build specialist services"
        echo "  --agents       Build agent services"
        echo "  --support      Build support services"
        echo "  --service NAME Build serviço específico"
        echo "  --list         Listar imagens no registry"
        echo "  --help         Mostrar ajuda"
        echo ""
        echo "Sem argumentos: modo interativo"
        ;;
    *)
        main
        ;;
esac
