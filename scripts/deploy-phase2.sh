#!/bin/bash
# =============================================================================
# Neural Hive-Mind - Script de Implantação Fase 2
# =============================================================================
# Serviços da Fase 2:
#   - service-registry      (Registro de serviços/agentes)
#   - scout-agents          (Agentes de exploração)
#   - worker-agents         (Agentes de execução)
#   - guard-agents          (Agentes de segurança)
#   - mcp-tool-catalog      (Catálogo de ferramentas MCP)
#   - code-forge            (Geração de código)
#   - execution-ticket-service (Tickets de execução)
#   - self-healing-engine   (Motor de auto-cura)
#   - queen-agent           (Agente rainha - coordenação)
# =============================================================================

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações
REGISTRY="37.60.241.150:30500"
NAMESPACE="neural-hive"
HELM_CHARTS_DIR="/jimy/Neural-Hive-Mind/helm-charts"
SERVICES_DIR="/jimy/Neural-Hive-Mind/services"

# Lista de serviços da Fase 2
PHASE2_SERVICES=(
    "service-registry"
    "scout-agents"
    "worker-agents"
    "guard-agents"
    "mcp-tool-catalog"
    "code-forge"
    "execution-ticket-service"
    "self-healing-engine"
    "queen-agent"
)

# Funções auxiliares
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo ""
    echo "============================================================================="
    echo -e "${BLUE}$1${NC}"
    echo "============================================================================="
}

check_prerequisites() {
    print_header "Verificando pré-requisitos"

    # Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker não encontrado. Instale o Docker primeiro."
        exit 1
    fi
    log_success "Docker encontrado: $(docker --version)"

    # kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado. Instale o kubectl primeiro."
        exit 1
    fi
    log_success "kubectl encontrado: $(kubectl version --client --short 2>/dev/null || kubectl version --client)"

    # helm
    if ! command -v helm &> /dev/null; then
        log_error "Helm não encontrado. Instale o Helm primeiro."
        exit 1
    fi
    log_success "Helm encontrado: $(helm version --short)"

    # Verificar conexão com cluster
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Não foi possível conectar ao cluster Kubernetes."
        exit 1
    fi
    log_success "Conectado ao cluster Kubernetes"

    # Verificar se registry está acessível
    if ! curl -s http://${REGISTRY}/v2/_catalog &> /dev/null; then
        log_warn "Registry ${REGISTRY} pode não estar acessível"
    else
        log_success "Registry ${REGISTRY} acessível"
    fi
}

build_and_push_image() {
    local service=$1
    local dockerfile_path="${SERVICES_DIR}/${service}/Dockerfile"
    local image_name="${REGISTRY}/${service}:latest"

    if [ ! -f "$dockerfile_path" ]; then
        log_warn "Dockerfile não encontrado para ${service} em ${dockerfile_path}"
        return 1
    fi

    log_info "Building ${service}..."

    cd /jimy/Neural-Hive-Mind

    # Build da imagem
    if docker build -f "$dockerfile_path" -t "$image_name" . ; then
        log_success "Build de ${service} concluído"

        # Push para registry
        log_info "Pushing ${service} para registry..."
        if docker push "$image_name"; then
            log_success "Push de ${service} concluído"
            return 0
        else
            log_error "Falha no push de ${service}"
            return 1
        fi
    else
        log_error "Falha no build de ${service}"
        return 1
    fi
}

deploy_with_helm() {
    local service=$1
    local chart_path="${HELM_CHARTS_DIR}/${service}"
    local values_file="${chart_path}/values-local.yaml"

    if [ ! -d "$chart_path" ]; then
        log_warn "Helm chart não encontrado para ${service} em ${chart_path}"
        return 1
    fi

    log_info "Deploying ${service} com Helm..."

    # Verificar se values-local existe
    local values_args=""
    if [ -f "$values_file" ]; then
        values_args="-f ${values_file}"
    fi

    # Deploy com Helm
    if helm upgrade --install "$service" "$chart_path" \
        --namespace "$NAMESPACE" \
        --create-namespace \
        $values_args \
        --set image.repository="${REGISTRY}/${service}" \
        --set image.tag="latest" \
        --set image.pullPolicy="Always" \
        --wait \
        --timeout 5m; then
        log_success "Deploy de ${service} concluído"
        return 0
    else
        log_error "Falha no deploy de ${service}"
        return 1
    fi
}

show_status() {
    print_header "Status dos Serviços Fase 2"

    echo ""
    echo "Pods no namespace ${NAMESPACE}:"
    kubectl get pods -n "$NAMESPACE" -o wide

    echo ""
    echo "Services no namespace ${NAMESPACE}:"
    kubectl get svc -n "$NAMESPACE"
}

# Menu de opções
show_menu() {
    echo ""
    echo "============================================================================="
    echo -e "${BLUE}Neural Hive-Mind - Implantação Fase 2${NC}"
    echo "============================================================================="
    echo ""
    echo "Opções disponíveis:"
    echo "  1) Build e push de todas as imagens"
    echo "  2) Deploy de todos os serviços"
    echo "  3) Build, push e deploy completo"
    echo "  4) Build/push de um serviço específico"
    echo "  5) Deploy de um serviço específico"
    echo "  6) Mostrar status dos serviços"
    echo "  7) Sair"
    echo ""
}

select_service() {
    echo ""
    echo "Serviços disponíveis:"
    for i in "${!PHASE2_SERVICES[@]}"; do
        echo "  $((i+1))) ${PHASE2_SERVICES[$i]}"
    done
    echo ""
    read -p "Selecione o serviço (1-${#PHASE2_SERVICES[@]}): " selection

    if [[ "$selection" =~ ^[0-9]+$ ]] && [ "$selection" -ge 1 ] && [ "$selection" -le "${#PHASE2_SERVICES[@]}" ]; then
        echo "${PHASE2_SERVICES[$((selection-1))]}"
    else
        echo ""
    fi
}

build_all() {
    print_header "Building todas as imagens da Fase 2"

    local success=0
    local failed=0

    for service in "${PHASE2_SERVICES[@]}"; do
        if build_and_push_image "$service"; then
            ((success++))
        else
            ((failed++))
        fi
    done

    echo ""
    log_info "Resumo: ${success} sucesso, ${failed} falhas"
}

deploy_all() {
    print_header "Deploying todos os serviços da Fase 2"

    local success=0
    local failed=0

    for service in "${PHASE2_SERVICES[@]}"; do
        if deploy_with_helm "$service"; then
            ((success++))
        else
            ((failed++))
        fi
    done

    echo ""
    log_info "Resumo: ${success} sucesso, ${failed} falhas"

    show_status
}

# Execução principal
main() {
    check_prerequisites

    while true; do
        show_menu
        read -p "Escolha uma opção: " option

        case $option in
            1)
                build_all
                ;;
            2)
                deploy_all
                ;;
            3)
                build_all
                deploy_all
                ;;
            4)
                service=$(select_service)
                if [ -n "$service" ]; then
                    build_and_push_image "$service"
                else
                    log_error "Seleção inválida"
                fi
                ;;
            5)
                service=$(select_service)
                if [ -n "$service" ]; then
                    deploy_with_helm "$service"
                else
                    log_error "Seleção inválida"
                fi
                ;;
            6)
                show_status
                ;;
            7)
                log_info "Saindo..."
                exit 0
                ;;
            *)
                log_error "Opção inválida"
                ;;
        esac
    done
}

# Permitir execução direta com argumentos
if [ "$1" == "--build-all" ]; then
    check_prerequisites
    build_all
elif [ "$1" == "--deploy-all" ]; then
    check_prerequisites
    deploy_all
elif [ "$1" == "--full" ]; then
    check_prerequisites
    build_all
    deploy_all
elif [ "$1" == "--status" ]; then
    show_status
elif [ "$1" == "--build" ] && [ -n "$2" ]; then
    check_prerequisites
    build_and_push_image "$2"
elif [ "$1" == "--deploy" ] && [ -n "$2" ]; then
    check_prerequisites
    deploy_with_helm "$2"
else
    main
fi
