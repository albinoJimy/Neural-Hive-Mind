#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/security-functions.sh"
SCRIPT_DIR="${SECURITY_ROOT}"

vault_init() {
    log_section "Inicializando Vault"
    vault_check_health || return 1
    vault_enable_auth_methods kubernetes
    vault_enable_secrets_engines kv pki
    vault_create_policies "${SCRIPT_DIR}/modules/vault/policies"
    vault_create_roles "${SCRIPT_DIR}/modules/vault/roles.csv"

    if [[ -x "${SCRIPT_DIR}/modules/vault/init.sh" ]]; then
        log_info "Executando script legado de init"
        DRY_RUN="${DRY_RUN}" "${SCRIPT_DIR}/modules/vault/init.sh" "$@"
    fi
    if [[ -x "${SCRIPT_DIR}/modules/vault/configure.sh" ]]; then
        log_info "Executando script legado de configuração"
        DRY_RUN="${DRY_RUN}" "${SCRIPT_DIR}/modules/vault/configure.sh" "$@"
    fi
    log_success "Vault inicializado"
}

vault_configure() {
    if [[ -x "${SCRIPT_DIR}/modules/vault/configure.sh" ]]; then
        log_info "Configurando Vault (policies/roles)"
        DRY_RUN="${DRY_RUN}" "${SCRIPT_DIR}/modules/vault/configure.sh" "$@"
    else
        log_warning "Script de configuração não encontrado"
    fi
}

vault_populate() {
    local mode="${1:-static}"
    local environment="${2:-dev}"
    if [[ -x "${SCRIPT_DIR}/modules/vault/populate.sh" ]]; then
        DRY_RUN="${DRY_RUN}" "${SCRIPT_DIR}/modules/vault/populate.sh" \
            --mode "${mode}" \
            --environment "${environment}"
    else
        log_warning "Script de popular secrets não encontrado"
    fi
}

vault_pki() {
    if [[ -x "${SCRIPT_DIR}/modules/vault/pki.sh" ]]; then
        DRY_RUN="${DRY_RUN}" "${SCRIPT_DIR}/modules/vault/pki.sh" "$@"
    else
        log_warning "Script de PKI não encontrado"
    fi
}

vault_deploy_ha() {
    if [[ -x "${SCRIPT_DIR}/modules/vault/deploy-ha.sh" ]]; then
        DRY_RUN="${DRY_RUN}" "${SCRIPT_DIR}/modules/vault/deploy-ha.sh" "$@"
    else
        log_warning "Script de deploy HA não encontrado"
    fi
}

vault_backup() {
    local output="${1:-/tmp/vault-backup-$(date +%Y%m%d).tar.gz}"
    log_info "Criando backup Vault em ${output}"
    local snapshot="/tmp/snapshot.snap"
    if [[ "${DRY_RUN}" != "true" ]]; then
        kubectl exec -n "${VAULT_NAMESPACE}" "${VAULT_POD}" -- vault operator raft snapshot save "${snapshot}"
        kubectl cp "${VAULT_NAMESPACE}/${VAULT_POD}:${snapshot}" "${output}"
        log_success "Backup criado: ${output}"
    else
        log_info "[dry-run] vault operator raft snapshot save ${snapshot}"
        log_info "[dry-run] kubectl cp ${VAULT_NAMESPACE}/${VAULT_POD}:${snapshot} ${output}"
    fi
}

vault_restore() {
    local input="$1"
    if [[ ! -f "${input}" ]]; then
        log_error "Arquivo de backup não encontrado: ${input}"
        return 1
    fi
    log_info "Restaurando snapshot Vault de ${input}"
    if [[ "${DRY_RUN}" != "true" ]]; then
        kubectl cp "${input}" "${VAULT_NAMESPACE}/${VAULT_POD}:/tmp/restore.snap"
        kubectl exec -n "${VAULT_NAMESPACE}" "${VAULT_POD}" -- vault operator raft snapshot restore /tmp/restore.snap
        log_success "Restaurado com sucesso"
    else
        log_info "[dry-run] Restauraria snapshot ${input}"
    fi
}

vault_audit() {
    log_info "Consultando audit devices Vault"
    vault_exec audit list || log_warning "Não foi possível listar audit devices"
}

export -f vault_init vault_configure vault_populate vault_backup vault_restore vault_audit vault_pki vault_deploy_ha
