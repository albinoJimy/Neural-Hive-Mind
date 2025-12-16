#!/usr/bin/env bash
set -euo pipefail

SECURITY_ROOT="${SECURITY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SCRIPTS_ROOT="${SCRIPTS_ROOT:-$(cd "${SECURITY_ROOT}/.." && pwd)}"
SECURITY_MODULES_DIR="${SECURITY_MODULES_DIR:-${SECURITY_ROOT}/modules}"

# Shared libs
source "${SCRIPTS_ROOT}/lib/common.sh"
source "${SCRIPTS_ROOT}/lib/k8s.sh"

DRY_RUN="${DRY_RUN:-false}"
VAULT_NAMESPACE="${VAULT_NAMESPACE:-vault}"
VAULT_POD="${VAULT_POD:-vault-0}"
SPIRE_NAMESPACE="${SPIRE_NAMESPACE:-spire-system}"
SPIRE_POD="${SPIRE_POD:-spire-server-0}"

run_cmd() {
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[dry-run] $*"
        return 0
    fi
    "$@"
}

vault_exec() {
    local namespace="${VAULT_NAMESPACE}"
    local pod="${VAULT_POD}"
    k8s_exec_in_pod "${namespace}" "${pod}" vault "$@"
}

vault_check_health() {
    log_info "Verificando health do Vault"
    if vault_exec status >/dev/null 2>&1; then
        log_success "Vault acessível e respondendo"
        return 0
    fi
    log_error "Vault não está acessível"
    return 1
}

vault_enable_auth_method() {
    local method="$1"
    log_info "Habilitando método de auth Vault: ${method}"
    run_cmd vault_exec auth enable "${method}" || log_warning "Método ${method} já habilitado ou não pôde ser habilitado"
}

vault_enable_auth_methods() {
    local methods=("${@:-kubernetes}")
    for method in "${methods[@]}"; do
        vault_enable_auth_method "${method}"
    done
}

vault_enable_secrets_engine() {
    local engine="$1"
    local path="${2:-${engine}}"
    log_info "Habilitando secrets engine ${engine} em ${path}"
    run_cmd vault_exec secrets enable -path="${path}" "${engine}" || log_warning "Secrets engine ${engine} já habilitado"
}

vault_enable_secrets_engines() {
    local engines=("${@:-kv}")
    for engine in "${engines[@]}"; do
        vault_enable_secrets_engine "${engine}"
    done
}

vault_create_policy() {
    local name="$1"
    local file="$2"
    if [[ ! -f "${file}" ]]; then
        log_warning "Policy file não encontrado: ${file}"
        return 1
    fi
    log_info "Criando policy Vault ${name} a partir de ${file}"
    run_cmd vault_exec policy write "${name}" "${file}"
}

vault_create_role() {
    local role_name="$1"
    local sa="$2"
    local namespace="$3"
    local policies="$4"

    log_info "Criando role Vault ${role_name} (sa=${sa}, ns=${namespace}, policies=${policies})"
    run_cmd vault_exec write "auth/kubernetes/role/${role_name}" \
        bound_service_account_names="${sa}" \
        bound_service_account_namespaces="${namespace}" \
        policies="${policies}" \
        ttl=1h
}

vault_create_policies() {
    local policies_dir="$1"
    if [[ ! -d "${policies_dir}" ]]; then
        log_warning "Diretório de policies não encontrado: ${policies_dir}"
        return 0
    fi
    local policy
    for policy in "${policies_dir}"/*.hcl; do
        [[ -e "${policy}" ]] || continue
        local name
        name="$(basename "${policy}" .hcl)"
        vault_create_policy "${name}" "${policy}"
    done
}

vault_create_roles() {
    local roles_file="$1"
    if [[ ! -f "${roles_file}" ]]; then
        log_warning "Arquivo de roles não encontrado: ${roles_file}"
        return 0
    fi
    while IFS=',' read -r role_name sa ns policies; do
        [[ -z "${role_name}" ]] && continue
        vault_create_role "${role_name}" "${sa}" "${ns}" "${policies}"
    done < "${roles_file}"
}

spire_exec() {
    local namespace="${SPIRE_NAMESPACE}"
    local pod="${SPIRE_POD}"
    k8s_exec_in_pod "${namespace}" "${pod}" spire-server "$@"
}

spire_check_health() {
    log_info "Verificando health do SPIRE server"
    if spire_exec healthcheck >/dev/null 2>&1; then
        log_success "SPIRE server saudável"
        return 0
    fi
    log_error "SPIRE server não está saudável"
    return 1
}

spire_create_entry() {
    local spiffe_id="$1"
    local parent_id="${2:-spiffe://example.org/ns/${SPIRE_NAMESPACE}/sa/default}"
    local selector="${3:-k8s:sa:default}"

    log_info "Criando registration entry ${spiffe_id}"
    run_cmd spire_exec entry create \
        -spiffeID "${spiffe_id}" \
        -parentID "${parent_id}" \
        -selector "${selector}"
}

spire_fetch_jwt_svid() {
    local audience="$1"
    local spiffe_id="$2"
    log_info "Obtendo JWT-SVID para ${spiffe_id}"
    run_cmd spire_exec token mint -audience "${audience}" -spiffeID "${spiffe_id}"
}

cert_check_expiry() {
    local days_threshold="${1:-30}"
    log_info "Verificando expiração de certificados (< ${days_threshold} dias)"
    if command -v jq >/dev/null 2>&1; then
        kubectl get certificates --all-namespaces -o json \
            | jq -r --arg days "${days_threshold}" \
                '.items[] | {ns:.metadata.namespace,name:.metadata.name,notAfter:.status.notAfter} \
                | select(.notAfter!=null) \
                | select(((.notAfter|fromdateiso8601) - now) < ($days|tonumber*24*60*60)) \
                | "[WARN] Cert \(.ns)/\(.name) expira em \(.notAfter)"' \
            | while read -r line; do log_warning "${line}"; done || true
    else
        log_warning "jq não encontrado; listando certificados sem validar datas"
        kubectl get certificates --all-namespaces || true
    fi
}

cert_create_self_signed() {
    local cn="${1:-neural-hive.local}"
    local out_dir="${2:-/tmp/security-certs}"
    mkdir -p "${out_dir}"
    log_info "Gerando certificado self-signed para CN=${cn} em ${out_dir}"
    run_cmd openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "${out_dir}/tls.key" \
        -out "${out_dir}/tls.crt" \
        -subj "/CN=${cn}"
}

cert_manager_wait_ready() {
    local namespace="${1:-cert-manager}"
    log_info "Aguardando cert-manager em ${namespace}"
    run_cmd kubectl wait -n "${namespace}" --for=condition=Available deployment/cert-manager --timeout=180s
}

secrets_generate_password() {
    local length="${1:-32}"
    LC_ALL=C tr -dc 'A-Za-z0-9!@#$%&*' < /dev/urandom | head -c "${length}"
}

secrets_create_k8s() {
    local namespace="$1"
    local name="$2"
    shift 2
    log_info "Criando secret ${name} em ${namespace}"
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[dry-run] kubectl create secret generic ${name} -n ${namespace} $*"
        return 0
    fi
    k8s_create_secret "${namespace}" "${name}" "$@"
}

secrets_rotate() {
    local namespace="$1"
    local name="$2"
    log_info "Rotacionando secret ${namespace}/${name}"
    if [[ "${DRY_RUN}" != "true" ]]; then
        k8s_delete_secret "${namespace}" "${name}" || true
    else
        log_info "[dry-run] kubectl delete secret ${name} -n ${namespace}"
    fi
}

validate_mtls_connectivity() {
    local namespace="${1:-default}"
    local source="${2:-orchestrator}"
    local target="${3:-worker}"
    if declare -F k8s_test_mtls_connectivity >/dev/null; then
        k8s_test_mtls_connectivity "${namespace}" "${source}" "${target}"
    elif [[ -x "${SCRIPTS_ROOT}/validation/test-mtls-connectivity.sh" ]]; then
        "${SCRIPTS_ROOT}/validation/test-mtls-connectivity.sh"
    else
        log_warning "Não foi possível validar mTLS: script ou função indisponível"
    fi
}

validate_oauth2_flow() {
    if [[ -x "${SCRIPTS_ROOT}/validation/validate-oauth2-flow.sh" ]]; then
        "${SCRIPTS_ROOT}/validation/validate-oauth2-flow.sh"
    else
        log_warning "Script de validação OAuth2 não encontrado"
    fi
}

validate_policy_enforcement() {
    if [[ -x "${SCRIPTS_ROOT}/validation/validate-policy-enforcement.sh" ]]; then
        "${SCRIPTS_ROOT}/validation/validate-policy-enforcement.sh"
    else
        log_warning "Script de validação de políticas não encontrado"
    fi
}

validate_namespace_isolation() {
    if [[ -x "${SCRIPTS_ROOT}/validation/validate-namespace-isolation.sh" ]]; then
        "${SCRIPTS_ROOT}/validation/validate-namespace-isolation.sh"
    else
        log_warning "Script de isolamento de namespace não encontrado"
    fi
}

export -f vault_exec vault_check_health vault_enable_auth_method vault_enable_auth_methods vault_enable_secrets_engine
export -f vault_enable_secrets_engines vault_create_policy vault_create_policies vault_create_role vault_create_roles
export -f spire_exec spire_check_health spire_create_entry spire_fetch_jwt_svid
export -f cert_check_expiry cert_create_self_signed cert_manager_wait_ready
export -f secrets_generate_password secrets_create_k8s secrets_rotate
export -f validate_mtls_connectivity validate_oauth2_flow validate_policy_enforcement validate_namespace_isolation
