#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/security-functions.sh"
SCRIPT_DIR="${SECURITY_ROOT}"

certs_setup() {
    local environment="${1:-dev}"
    if [[ -x "${SCRIPT_DIR}/modules/certificates/setup.sh" ]]; then
        ENV="${environment}" DRY_RUN="${DRY_RUN}" "${SCRIPT_DIR}/modules/certificates/setup.sh" "$@"
    else
        log_warning "Script setup-cert-manager não encontrado"
    fi
}

certs_generate() {
    local type="${1:-self-signed}"
    local cn="${2:-neural-hive.local}"
    case "${type}" in
        self-signed)
            cert_create_self_signed "${cn}" "${3:-/tmp/security-certs}";;
        *)
            if [[ -x "${SCRIPT_DIR}/setup-observability-secrets.sh" ]]; then
                DRY_RUN="${DRY_RUN}" "${SCRIPT_DIR}/setup-observability-secrets.sh" "$@"
            else
                log_warning "Tipo de certificado não suportado: ${type}"
            fi
            ;;
    esac
}

certs_validate() {
    local check_expiry="${1:-true}"
    local days="${2:-30}"
    log_info "Validando certificados"
    if [[ "${check_expiry}" == "true" ]]; then
        cert_check_expiry "${days}"
    fi
    cert_manager_wait_ready || true
}

certs_rotate() {
    local service="$1"
    log_info "Rotacionando certificados para ${service}"
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[dry-run] Rotacionaria certificados de ${service}"
        return 0
    fi
    kubectl delete secret -l app="${service}" --all-namespaces || true
    certs_generate self-signed "${service}" "/tmp/security-certs-${service}"
}

export -f certs_setup certs_generate certs_validate certs_rotate
