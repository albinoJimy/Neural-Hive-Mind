#!/bin/bash
#===============================================================================
# migrate-to-ghcr.sh
# Migra deployments do registry interno para GitHub Container Registry (GHCR)
#===============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

NAMESPACE="${NAMESPACE:-neural-hive}"
GHCR_USER="${GHCR_USER:-albinojimy}"
GHCR_PREFIX="ghcr.io/${GHCR_USER}/neural-hive-mind"
SECRET_NAME="ghcr-secret"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DRY_RUN="${DRY_RUN:-false}"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${CYAN}[STEP]${NC} $1"; }

print_header() {
    echo ""
    echo "=============================================================================="
    echo -e "${BLUE}$1${NC}"
    echo "=============================================================================="
}

# Lista de servicos para migrar
SERVICES=(
    "analyst-agents"
    "code-forge"
    "execution-ticket-service"
    "explainability-api"
    "gateway-intencoes"
    "guard-agents"
    "mcp-tool-catalog"
    "memory-layer-api"
    "orchestrator-dynamic"
    "queen-agent"
    "scout-agents"
    "self-healing-engine"
    "service-registry"
    "sla-management-system"
)

usage() {
    cat <<EOF
Uso: $0 [OPCOES]

Migra deployments do registry interno para GitHub Container Registry (GHCR).

OPCOES:
    -u, --user <user>         GitHub username (padrao: $GHCR_USER)
    -t, --tag <tag>           Tag da imagem (padrao: $IMAGE_TAG)
    -n, --namespace <ns>      Namespace (padrao: $NAMESPACE)
    -s, --services <list>     Servicos especificos (separados por virgula)
    --dry-run                 Apenas mostrar o que seria feito
    --rollback                Reverter para registry interno
    -h, --help                Mostrar ajuda

EXEMPLOS:
    # Migrar todos os servicos
    $0

    # Migrar com tag especifica
    $0 -t 1.0.8

    # Migrar servicos especificos
    $0 -s "gateway-intencoes,queen-agent"

    # Dry run
    $0 --dry-run

    # Rollback para registry interno
    $0 --rollback

EOF
}

# Verificar pre-requisitos
check_prerequisites() {
    log_step "Verificando pre-requisitos..."
    
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Nao foi possivel conectar ao cluster"
        exit 1
    fi
    
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_error "Namespace $NAMESPACE nao existe"
        exit 1
    fi
    
    if ! kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" &> /dev/null; then
        log_error "Secret $SECRET_NAME nao encontrado"
        log_info "Execute primeiro: ./scripts/ghcr/setup-ghcr-secret.sh"
        exit 1
    fi
    
    log_success "Pre-requisitos OK"
}

# Adicionar imagePullSecrets ao deployment
add_image_pull_secret() {
    local DEPLOYMENT="$1"
    
    # Verificar se ja tem o secret
    local HAS_SECRET=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" \
        -o jsonpath='{.spec.template.spec.imagePullSecrets[?(@.name=="'"$SECRET_NAME"'")].name}' 2>/dev/null || echo "")
    
    if [[ -n "$HAS_SECRET" ]]; then
        log_info "  imagePullSecrets ja configurado"
        return 0
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "  [DRY-RUN] Adicionaria imagePullSecrets"
        return 0
    fi
    
    # Adicionar imagePullSecrets via patch
    kubectl patch deployment "$DEPLOYMENT" -n "$NAMESPACE" \
        --type='json' \
        -p='[{"op": "add", "path": "/spec/template/spec/imagePullSecrets", "value": [{"name": "'"$SECRET_NAME"'"}]}]' 2>/dev/null || \
    kubectl patch deployment "$DEPLOYMENT" -n "$NAMESPACE" \
        --type='json' \
        -p='[{"op": "replace", "path": "/spec/template/spec/imagePullSecrets", "value": [{"name": "'"$SECRET_NAME"'"}]}]'
}

# Atualizar imagem do deployment
update_deployment_image() {
    local SERVICE="$1"
    local NEW_IMAGE="${GHCR_PREFIX}/${SERVICE}:${IMAGE_TAG}"
    
    log_step "Atualizando $SERVICE"
    
    # Verificar se deployment existe
    if ! kubectl get deployment "$SERVICE" -n "$NAMESPACE" &> /dev/null; then
        log_warn "  Deployment $SERVICE nao encontrado - pulando"
        return 1
    fi
    
    # Obter imagem atual
    local CURRENT_IMAGE=$(kubectl get deployment "$SERVICE" -n "$NAMESPACE" \
        -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "unknown")
    
    log_info "  Imagem atual: $CURRENT_IMAGE"
    log_info "  Nova imagem:  $NEW_IMAGE"
    
    # Adicionar imagePullSecrets
    add_image_pull_secret "$SERVICE"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "  [DRY-RUN] Atualizaria imagem"
        return 0
    fi
    
    # Atualizar imagem
    if kubectl set image deployment/"$SERVICE" "$SERVICE"="$NEW_IMAGE" -n "$NAMESPACE" 2>/dev/null; then
        log_success "  Imagem atualizada"
        return 0
    else
        # Tentar com nome de container generico
        kubectl set image deployment/"$SERVICE" "*"="$NEW_IMAGE" -n "$NAMESPACE" 2>/dev/null || {
            log_error "  Falha ao atualizar imagem"
            return 1
        }
    fi
}

# Rollback para registry interno
rollback_deployment() {
    local SERVICE="$1"
    local INTERNAL_REGISTRY="37.60.241.150:30500"
    
    log_step "Rollback $SERVICE"
    
    if ! kubectl get deployment "$SERVICE" -n "$NAMESPACE" &> /dev/null; then
        log_warn "  Deployment $SERVICE nao encontrado - pulando"
        return 1
    fi
    
    # Obter tag atual
    local CURRENT_TAG=$(kubectl get deployment "$SERVICE" -n "$NAMESPACE" \
        -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null | sed 's/.*://')
    
    local OLD_IMAGE="${INTERNAL_REGISTRY}/${SERVICE}:${CURRENT_TAG:-latest}"
    
    log_info "  Revertendo para: $OLD_IMAGE"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "  [DRY-RUN] Reverteria imagem"
        return 0
    fi
    
    kubectl set image deployment/"$SERVICE" "$SERVICE"="$OLD_IMAGE" -n "$NAMESPACE" 2>/dev/null || \
    kubectl set image deployment/"$SERVICE" "*"="$OLD_IMAGE" -n "$NAMESPACE"
}

# Migrar todos os servicos
migrate_all() {
    print_header "Migrando Deployments para GHCR"
    
    log_info "GHCR Prefix: $GHCR_PREFIX"
    log_info "Tag: $IMAGE_TAG"
    log_info "Namespace: $NAMESPACE"
    log_info "Servicos: ${#SERVICES[@]}"
    echo ""
    
    local SUCCESS=()
    local FAILED=()
    local SKIPPED=()
    
    for SERVICE in "${SERVICES[@]}"; do
        if update_deployment_image "$SERVICE"; then
            SUCCESS+=("$SERVICE")
        else
            if kubectl get deployment "$SERVICE" -n "$NAMESPACE" &> /dev/null; then
                FAILED+=("$SERVICE")
            else
                SKIPPED+=("$SERVICE")
            fi
        fi
        echo ""
    done
    
    # Resumo
    print_header "Resumo da Migracao"
    
    echo -e "${GREEN}Sucesso: ${#SUCCESS[@]}${NC}"
    for s in "${SUCCESS[@]}"; do
        echo "  - $s"
    done
    
    if [[ ${#SKIPPED[@]} -gt 0 ]]; then
        echo -e "${YELLOW}Pulados: ${#SKIPPED[@]}${NC}"
        for s in "${SKIPPED[@]}"; do
            echo "  - $s"
        done
    fi
    
    if [[ ${#FAILED[@]} -gt 0 ]]; then
        echo -e "${RED}Falhas: ${#FAILED[@]}${NC}"
        for s in "${FAILED[@]}"; do
            echo "  - $s"
        done
        return 1
    fi
    
    return 0
}

# Rollback todos os servicos
rollback_all() {
    print_header "Rollback para Registry Interno"
    
    for SERVICE in "${SERVICES[@]}"; do
        rollback_deployment "$SERVICE"
        echo ""
    done
}

# Verificar status dos deployments
check_status() {
    print_header "Status dos Deployments"
    
    echo ""
    printf "%-30s %-50s %-10s\n" "DEPLOYMENT" "IMAGE" "READY"
    printf "%-30s %-50s %-10s\n" "----------" "-----" "-----"
    
    for SERVICE in "${SERVICES[@]}"; do
        if kubectl get deployment "$SERVICE" -n "$NAMESPACE" &> /dev/null; then
            local IMAGE=$(kubectl get deployment "$SERVICE" -n "$NAMESPACE" \
                -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null | cut -c1-48)
            local READY=$(kubectl get deployment "$SERVICE" -n "$NAMESPACE" \
                -o jsonpath='{.status.readyReplicas}/{.status.replicas}' 2>/dev/null || echo "?/?")
            printf "%-30s %-50s %-10s\n" "$SERVICE" "${IMAGE}..." "$READY"
        fi
    done
}

# Parse argumentos
ROLLBACK="false"
STATUS_ONLY="false"

while [[ $# -gt 0 ]]; do
    case $1 in
        -u|--user)
            GHCR_USER="$2"
            GHCR_PREFIX="ghcr.io/${GHCR_USER}/neural-hive-mind"
            shift 2
            ;;
        -t|--tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -s|--services)
            IFS=',' read -ra SERVICES <<< "$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        --rollback)
            ROLLBACK="true"
            shift
            ;;
        --status)
            STATUS_ONLY="true"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "Opcao desconhecida: $1"
            usage
            exit 1
            ;;
    esac
done

# Main
main() {
    if [[ "$STATUS_ONLY" == "true" ]]; then
        check_status
        exit 0
    fi
    
    check_prerequisites
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "Modo DRY-RUN - nenhuma alteracao sera feita"
        echo ""
    fi
    
    if [[ "$ROLLBACK" == "true" ]]; then
        rollback_all
    else
        migrate_all
    fi
    
    echo ""
    log_info "Verificando status final..."
    check_status
}

main
