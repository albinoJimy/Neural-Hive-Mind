#!/bin/bash
# Unified Gateway - Traffic Shift Script
# Facilita a transição gradual de tráfego entre gateway-intencoes e unified-gateway
#
# Uso: ./traffic-shift.sh <phase>
#   phase: 1 | 2 | 3 | rollback
#
# Phases:
#   1 - 10% unified-gateway, 90% gateway-intencoes
#   2 - 50% unified-gateway, 50% gateway-intencoes
#   3 - 100% unified-gateway (migration complete)
#   rollback - Reverte para 100% gateway-intencoes

set -e

NAMESPACE="gateway"
VS_NAME="unified-gateway-vs"
VS_FILE="k8s/unified-gateway-virtualservice.yaml"

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

# Verificar se kubectl está disponível
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl não encontrado. Instale kubectl primeiro."
        exit 1
    fi
}

# Verificar se o VirtualService existe
check_vs_exists() {
    if ! kubectl get virtualservice "$VS_NAME" -n "$NAMESPACE" &> /dev/null; then
        log_warning "VirtualService $VS_NAME não encontrado. Criando..."
        kubectl apply -f "$VS_FILE"
        log_success "VirtualService criado."
    fi
}

# Obter configuração atual do traffic split
get_current_split() {
    kubectl get virtualservice "$VS_NAME" -n "$NAMESPACE" -o json | \
        jq -r '.spec.http[0].route[] | "\(.destination.host): \(.weight)%"' 2>/dev/null || \
        echo "Não foi possível obter configuração atual"
}

# Aplicar Phase 1: 10% unified-gateway
apply_phase1() {
    log_info "Aplicando Phase 1: 10% unified-gateway, 90% gateway-intencoes"
    kubectl patch virtualservice "$VS_NAME" -n "$NAMESPACE" --type=json \
        -p='[
            {"op": "replace", "path": "/spec/http/0/route/0/weight", "value": 90},
            {"op": "replace", "path": "/spec/http/0/route/1/weight", "value": 10}
        ]'
    log_success "Phase 1 aplicada. Tráfego: 10% → unified-gateway"
}

# Aplicar Phase 2: 50% unified-gateway
apply_phase2() {
    log_info "Aplicando Phase 2: 50% unified-gateway, 50% gateway-intencoes"
    kubectl patch virtualservice "$VS_NAME" -n "$NAMESPACE" --type=json \
        -p='[
            {"op": "replace", "path": "/spec/http/0/route/0/weight", "value": 50},
            {"op": "replace", "path": "/spec/http/0/route/1/weight", "value": 50}
        ]'
    log_success "Phase 2 aplicada. Tráfego: 50% → unified-gateway"
}

# Aplicar Phase 3: 100% unified-gateway
apply_phase3() {
    log_info "Aplicando Phase 3: 100% unified-gateway (migration complete)"
    kubectl patch virtualservice "$VS_NAME" -n "$NAMESPACE" --type=json \
        -p='[
            {"op": "replace", "path": "/spec/http/0/route/0/weight", "value": 0},
            {"op": "replace", "path": "/spec/http/0/route/1/weight", "value": 100}
        ]'
    log_success "Phase 3 aplicada. Tráfego: 100% → unified-gateway"
    log_warning "Após validação, gateway-intencoes pode ser desativado."
}

# Rollback para 100% gateway-intencoes
apply_rollback() {
    log_info "Aplicando Rollback: 100% gateway-intencoes"
    kubectl patch virtualservice "$VS_NAME" -n "$NAMESPACE" --type=json \
        -p='[
            {"op": "replace", "path": "/spec/http/0/route/0/weight", "value": 100},
            {"op": "replace", "path": "/spec/http/0/route/1/weight", "value": 0}
        ]'
    log_success "Rollback aplicado. Tráfego: 100% → gateway-intencoes (legado)"
}

# Mostrar status atual
show_status() {
    log_info "=== Traffic Split Status ==="
    echo ""
    get_current_split
    echo ""

    # Health checks
    log_info "=== Health Checks ==="
    echo ""
    echo "Unified Gateway:"
    kubectl get pods -n "$NAMESPACE" -l app=unified-gateway -o wide
    echo ""
    echo "Gateway Intencoes (Legacy):"
    kubectl get pods -n fluxo-a -l app=gateway-intencoes -o wide
    echo ""

    # Métricas recentes
    log_info "=== Recent Requests (last 5min) ==="
    echo ""
    kubectl exec -n "$NAMESPACE" deployment/unified-gateway -- \
        curl -s localhost:7999/metrics 2>/dev/null | \
        grep 'http_requests_total{' | tail -5 || echo "Não foi possível obter métricas"
}

# Função principal
main() {
    check_kubectl
    check_vs_exists

    case "${1:-}" in
        1)
            apply_phase1
            ;;
        2)
            apply_phase2
            ;;
        3)
            apply_phase3
            ;;
        rollback)
            apply_rollback
            ;;
        status)
            show_status
            ;;
        *)
            echo "Uso: $0 <phase>"
            echo ""
            echo "Phases:"
            echo "  1        - 10% unified-gateway, 90% gateway-intencoes"
            echo "  2        - 50% unified-gateway, 50% gateway-intencoes"
            echo "  3        - 100% unified-gateway (migration complete)"
            echo "  rollback - Reverte para 100% gateway-intencoes"
            echo "  status   - Mostra status atual do traffic split"
            echo ""
            exit 1
            ;;
    esac

    echo ""
    show_status
}

main "$@"
