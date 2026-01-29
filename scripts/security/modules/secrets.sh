#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/security-functions.sh"
SCRIPT_DIR="${SECURITY_ROOT}"

secrets_create() {
    local phase="${1:-2}"
    local mode="${2:-static}"
    local environment="${3:-dev}"
    local namespace="${4:-}"
    local service="${5:-}"

    if [[ "${phase}" == "2" && -x "${SCRIPT_DIR}/modules/secrets/create-phase2.sh" ]]; then
        local args=(--mode "${mode}" --environment "${environment}")
        [[ -n "${namespace}" ]] && args+=(--namespace "${namespace}")
        [[ -n "${service}" ]] && args+=(--service "${service}")

        DRY_RUN="${DRY_RUN}" "${SCRIPT_DIR}/modules/secrets/create-phase2.sh" "${args[@]}"
    else
        # Fallback: criar secret diretamente se script não existir
        if [[ -n "${namespace}" && -n "${service}" ]]; then
            log_info "Criando secret para ${service} em ${namespace} (fallback)"
            local secret_name="${service}-secret"
            local password
            password=$(secrets_generate_password 32)

            if [[ "${DRY_RUN}" != "true" ]]; then
                k8s_create_secret "${namespace}" "${secret_name}" \
                    --from-literal=password="${password}"
                log_success "Secret ${secret_name} criado em ${namespace}"
            else
                log_info "[dry-run] kubectl create secret generic ${secret_name} -n ${namespace}"
            fi
        else
            log_warning "Script de criação de secrets fase ${phase} não encontrado"
        fi
    fi
}

secrets_validate() {
    local phase="${1:-2}"
    if [[ "${phase}" == "2" && -x "${SCRIPT_DIR}/modules/secrets/validate-phase2.sh" ]]; then
        DRY_RUN="${DRY_RUN}" "${SCRIPT_DIR}/modules/secrets/validate-phase2.sh" "$@"
    else
        log_warning "Script de validação de secrets fase ${phase} não encontrado"
    fi
}

secrets_rotate() {
    local service="${1:?Erro: service é obrigatório}"
    local secret_name="${2:-${service}-secret}"
    local namespace="${3:-default}"
    local environment="${4:-dev}"

    log_info "Rotacionando secret ${secret_name} em ${namespace} (env: ${environment})"

    # Deletar secret existente
    if [[ "${DRY_RUN}" != "true" ]]; then
        if k8s_secret_exists "${namespace}" "${secret_name}"; then
            k8s_delete_secret "${namespace}" "${secret_name}" || true
            log_info "Secret ${secret_name} deletado"
        else
            log_warning "Secret ${secret_name} não existe em ${namespace}, será criado"
        fi
    else
        log_info "[dry-run] kubectl delete secret ${secret_name} -n ${namespace}"
    fi

    # Recriar secret com parâmetros corretos
    secrets_create "2" "static" "${environment}" "${namespace}" "${service}"
}

secrets_backup() {
    local output="${1:-/tmp/secrets-backup-$(date +%Y%m%d).yaml}"
    log_info "Exportando secrets para ${output}"
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[dry-run] kubectl get secrets --all-namespaces -o yaml > ${output}"
        return 0
    fi
    kubectl get secrets --all-namespaces -o yaml > "${output}"
    log_success "Backup de secrets salvo em ${output}"
}

secrets_restore() {
    local input="$1"
    if [[ ! -f "${input}" ]]; then
        log_error "Backup de secrets não encontrado: ${input}"
        return 1
    fi
    log_info "Restaurando secrets de ${input}"
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[dry-run] kubectl apply -f ${input}"
        return 0
    fi
    kubectl apply -f "${input}"
    log_success "Secrets restaurados"
}

export -f secrets_create secrets_validate secrets_rotate secrets_backup secrets_restore
