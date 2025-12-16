#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/security-functions.sh"
SCRIPT_DIR="${SECURITY_ROOT}"

spire_deploy() {
    local namespace="${1:-${SPIRE_NAMESPACE}}"
    if [[ -x "${SCRIPT_DIR}/modules/spire/deploy.sh" ]]; then
        DRY_RUN="${DRY_RUN}" "${SCRIPT_DIR}/modules/spire/deploy.sh" --namespace "${namespace}" "$@"
    else
        log_warning "Script de deploy SPIRE não encontrado"
    fi
}

spire_register() {
    local service="${1:-all}"
    log_info "Registrando SPIRE entries para ${service}"
    if [[ "${service}" == "all" && -x "${SCRIPT_DIR}/modules/spire/register-entries.sh" ]]; then
        DRY_RUN="${DRY_RUN}" "${SCRIPT_DIR}/modules/spire/register-entries.sh" "$@"
    elif [[ -x "${SCRIPT_DIR}/modules/spire/create-entries.sh" ]]; then
        DRY_RUN="${DRY_RUN}" "${SCRIPT_DIR}/modules/spire/create-entries.sh" "${service}" "$@"
    else
        spire_create_entry "${service}"
    fi
}

spire_validate() {
    log_info "Validando SPIRE"
    spire_check_health || return 1
    spire_exec entry show || true
}

spire_rotate() {
    log_info "Rotacionando certificados SPIRE"
    if [[ "${DRY_RUN}" != "true" ]]; then
        spire_exec bundle show || true
        spire_exec bundle prune || true
        log_success "Rotação executada (best-effort)"
    else
        log_info "[dry-run] spire bundle rotate"
    fi
}

export -f spire_deploy spire_register spire_validate spire_rotate
