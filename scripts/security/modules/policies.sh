#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/security-functions.sh"
SCRIPT_DIR="${SECURITY_ROOT}"

policies_transition() {
    local dry_run="${1:-false}"
    local threshold="${2:-10}"
    local min_days="${3:-3}"
    if [[ -x "${SCRIPT_DIR}/modules/policies/transition.sh" ]]; then
        DRY_RUN="${dry_run}" \
        MAX_VIOLATION_THRESHOLD="${threshold}" \
        MIN_DAYS_IN_WARN="${min_days}" \
            "${SCRIPT_DIR}/modules/policies/transition.sh"
    else
        log_warning "Script de transição de políticas não encontrado"
    fi
}

policies_validate() {
    local type="${1:-all}"
    case "${type}" in
        mtls)
            validate_mtls_connectivity ;;
        oauth2)
            validate_oauth2_flow ;;
        all)
            validate_policy_enforcement ;;
        *)
            log_warning "Tipo de validação desconhecido: ${type}" ;;
    esac
}

policies_audit() {
    local since="${1:-24h}"
    log_info "Auditando violações de políticas nas últimas ${since}"
    kubectl get events --all-namespaces --sort-by=.lastTimestamp \
        | grep -iE "denied|violation|policy" || true
}

export -f policies_transition policies_validate policies_audit
