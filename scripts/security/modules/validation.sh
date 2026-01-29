#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/security-functions.sh"
SCRIPT_DIR="${SECURITY_ROOT}"

validation_all() {
    log_section "Validando todos os componentes de segurança"
    local exit_code=0
    validation_vault || exit_code=1
    validation_mtls || exit_code=1
    validation_oauth2 || exit_code=1
    validation_policies || exit_code=1
    validation_namespace || exit_code=1
    return "${exit_code}"
}

validation_vault() {
    log_info "Validando Vault + SPIRE"
    if [[ -x "${SCRIPTS_ROOT}/test-vault-spiffe-connectivity.sh" ]]; then
        DRY_RUN="${DRY_RUN}" "${SCRIPTS_ROOT}/test-vault-spiffe-connectivity.sh" "$@"
    elif [[ -x "${SCRIPTS_ROOT}/validate-vault-spiffe-integration.sh" ]]; then
        DRY_RUN="${DRY_RUN}" "${SCRIPTS_ROOT}/validate-vault-spiffe-integration.sh" "$@"
    else
        log_warning "Scripts de validação Vault não encontrados"
    fi
}

validation_mtls() {
    log_info "Validando conectividade mTLS"
    if [[ -x "${SCRIPTS_ROOT}/validation/test-mtls-connectivity.sh" ]]; then
        DRY_RUN="${DRY_RUN}" "${SCRIPTS_ROOT}/validation/test-mtls-connectivity.sh" "$@"
    else
        validate_mtls_connectivity "$@"
    fi
}

validation_oauth2() {
    log_info "Validando fluxo OAuth2"
    if [[ -x "${SCRIPTS_ROOT}/validation/validate-oauth2-flow.sh" ]]; then
        DRY_RUN="${DRY_RUN}" "${SCRIPTS_ROOT}/validation/validate-oauth2-flow.sh" "$@"
    else
        validate_oauth2_flow "$@"
    fi
}

validation_policies() {
    log_info "Validando enforcement de políticas"
    if [[ -x "${SCRIPTS_ROOT}/validation/validate-policy-enforcement.sh" ]]; then
        DRY_RUN="${DRY_RUN}" "${SCRIPTS_ROOT}/validation/validate-policy-enforcement.sh" "$@"
    else
        validate_policy_enforcement "$@"
    fi
}

validation_namespace() {
    log_info "Validando isolamento de namespaces"
    if [[ -x "${SCRIPTS_ROOT}/validation/validate-namespace-isolation.sh" ]]; then
        DRY_RUN="${DRY_RUN}" "${SCRIPTS_ROOT}/validation/validate-namespace-isolation.sh" "$@"
    else
        validate_namespace_isolation "$@"
    fi
}

export -f validation_all validation_vault validation_mtls validation_oauth2 validation_policies validation_namespace
