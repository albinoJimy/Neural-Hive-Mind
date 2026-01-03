#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

declare -gA __K8S_NS_CACHE=()
declare -ga __K8S_PORT_FWD_PIDS=()

k8s_namespace_exists() {
    local namespace="$1"
    kubectl get namespace "${namespace}" >/dev/null 2>&1
}

k8s_create_namespace() {
    local namespace="$1"
    log_info "Garantindo namespace ${namespace}"
    kubectl create namespace "${namespace}" --dry-run=client -o yaml | kubectl apply -f -
}

k8s_delete_namespace() {
    local namespace="$1"
    log_warning "Removendo namespace ${namespace}"
    kubectl delete namespace "${namespace}" --wait=true
}

k8s_label_namespace() {
    local namespace="$1"
    shift
    log_info "Aplicando labels no namespace ${namespace}: $*"
    kubectl label namespace "${namespace}" "$@" --overwrite
}

k8s_detect_namespace() {
    local service="$1"
    if [[ -n "${__K8S_NS_CACHE[${service}]:-}" ]]; then
        echo "${__K8S_NS_CACHE[${service}]}"
        return 0
    fi
    local ns
    ns=$(kubectl get svc --all-namespaces | awk -v svc="${service}" '$2==svc {print $1; exit}')
    __K8S_NS_CACHE["${service}"]="${ns}"
    echo "${ns}"
}

k8s_get_pod_name() {
    local namespace="$1"
    local selector="$2"
    kubectl get pods -n "${namespace}" -l "${selector}" -o jsonpath='{.items[0].metadata.name}'
}

k8s_get_pod_logs() {
    local namespace="$1"
    local pod="$2"
    shift 2
    kubectl logs -n "${namespace}" "${pod}" "$@"
}

k8s_wait_for_pod_ready() {
    local namespace="$1"
    local selector="$2"
    local timeout="${3:-120}"

    log_info "Aguardando pods prontos em ${namespace} com seletor ${selector}"
    if ! kubectl wait --namespace "${namespace}" --for=condition=Ready pod -l "${selector}" --timeout="${timeout}s"; then
        log_error "Timeout aguardando pods com seletor ${selector}"
        return 1
    fi
}

k8s_exec_in_pod() {
    local namespace="$1"
    local pod="$2"
    shift 2
    kubectl exec -n "${namespace}" "${pod}" -- "$@"
}

k8s_get_pod_status() {
    local namespace="$1"
    local pod="$2"
    kubectl get pod -n "${namespace}" "${pod}" -o jsonpath='{.status.phase}'
}

k8s_get_pods_by_label() {
    local namespace="$1"
    local selector="$2"
    kubectl get pods -n "${namespace}" -l "${selector}" -o jsonpath='{.items[*].metadata.name}'
}

k8s_resource_exists() {
    local resource="$1"
    local name="$2"
    local namespace="${3:-}"
    local ns_flag=()
    [[ -n "${namespace}" ]] && ns_flag=(-n "${namespace}")
    kubectl get "${resource}" "${name}" "${ns_flag[@]}" >/dev/null 2>&1
}

k8s_apply_manifest() {
    local manifest="$1"
    log_info "Validando manifesto ${manifest}"
    kubectl apply --dry-run=client -f "${manifest}" >/dev/null
    log_info "Aplicando manifesto ${manifest}"
    kubectl apply -f "${manifest}"
}

k8s_delete_resource() {
    local resource="$1"
    local name="$2"
    local namespace="${3:-}"
    local ns_flag=()
    [[ -n "${namespace}" ]] && ns_flag=(-n "${namespace}")
    kubectl delete "${resource}" "${name}" "${ns_flag[@]}"
}

k8s_wait_for_resource() {
    local resource="$1"
    local name="$2"
    local condition="${3:-Ready}"
    local timeout="${4:-120}"
    local namespace="${5:-}"
    local ns_flag=()
    [[ -n "${namespace}" ]] && ns_flag=(-n "${namespace}")
    kubectl wait "${ns_flag[@]}" --for="condition=${condition}" "${resource}/${name}" --timeout="${timeout}s"
}

k8s_get_resource_status() {
    local resource="$1"
    local name="$2"
    local namespace="${3:-}"
    local ns_flag=()
    [[ -n "${namespace}" ]] && ns_flag=(-n "${namespace}")
    kubectl get "${resource}" "${name}" "${ns_flag[@]}" -o jsonpath='{.status}'
}

k8s_port_forward() {
    local namespace="$1"
    local resource="$2"
    local local_port="$3"
    local remote_port="$4"
    local retries="${5:-3}"

    log_info "Iniciando port-forward ${local_port}:${remote_port} para ${resource} em ${namespace}"
    local attempt=1
    while (( attempt <= retries )); do
        kubectl port-forward -n "${namespace}" "${resource}" "${local_port}:${remote_port}" >/dev/null 2>&1 &
        local pid=$!
        sleep 2
        if kill -0 "${pid}" >/dev/null 2>&1; then
            __K8S_PORT_FWD_PIDS+=("${pid}")
            echo "${pid}"
            return 0
        fi
        log_warning "Port-forward falhou (tentativa ${attempt}/${retries})."
        attempt=$((attempt + 1))
    done
    log_error "Não foi possível estabelecer port-forward para ${resource}"
    return 1
}

k8s_cleanup_port_forwards() {
    log_info "Encerrando port-forwards ativos (${#__K8S_PORT_FWD_PIDS[@]})"
    for pid in "${__K8S_PORT_FWD_PIDS[@]}"; do
        if kill -0 "${pid}" >/dev/null 2>&1; then
            kill "${pid}" || true
        fi
    done
    __K8S_PORT_FWD_PIDS=()
}

k8s_check_port_forward_active() {
    local pid="$1"
    kill -0 "${pid}" >/dev/null 2>&1
}

k8s_create_secret() {
    local namespace="$1"
    local name="$2"
    shift 2
    log_info "Criando secret ${name} em ${namespace}"
    kubectl create secret generic "${name}" -n "${namespace}" "$@" --dry-run=client -o yaml | kubectl apply -f -
}

k8s_secret_exists() {
    local namespace="$1"
    local name="$2"
    kubectl get secret -n "${namespace}" "${name}" >/dev/null 2>&1
}

k8s_delete_secret() {
    local namespace="$1"
    local name="$2"
    kubectl delete secret -n "${namespace}" "${name}"
}

k8s_test_service_connectivity() {
    local namespace="$1"
    local service_url="$2"
    local pod_name="tmp-connectivity-$(generate_random_string 5)"

    log_info "Testando conectividade para ${service_url} a partir do namespace ${namespace}"
    kubectl run "${pod_name}" -n "${namespace}" --image=curlimages/curl --restart=Never --command -- sleep 3600 >/dev/null
    kubectl wait -n "${namespace}" --for=condition=Ready "pod/${pod_name}" --timeout=60s

    if kubectl exec -n "${namespace}" "${pod_name}" -- curl -sSf "${service_url}" >/dev/null; then
        log_success "Conectividade para ${service_url} validada"
        kubectl delete pod -n "${namespace}" "${pod_name}" --force --grace-period=0 >/dev/null
        return 0
    fi

    log_error "Falha ao conectar em ${service_url}"
    kubectl delete pod -n "${namespace}" "${pod_name}" --force --grace-period=0 >/dev/null
    return 1
}

k8s_test_dns_resolution() {
    local namespace="$1"
    local host="$2"
    local pod_name="tmp-dns-$(generate_random_string 5)"

    log_info "Testando resolução DNS para ${host} em ${namespace}"
    kubectl run "${pod_name}" -n "${namespace}" --image=busybox --restart=Never --command -- sleep 3600 >/dev/null
    kubectl wait -n "${namespace}" --for=condition=Ready "pod/${pod_name}" --timeout=60s

    if kubectl exec -n "${namespace}" "${pod_name}" -- nslookup "${host}" >/dev/null 2>&1; then
        log_success "DNS resolvido para ${host}"
        kubectl delete pod -n "${namespace}" "${pod_name}" --force --grace-period=0 >/dev/null
        return 0
    fi

    log_error "Falha ao resolver DNS para ${host}"
    kubectl delete pod -n "${namespace}" "${pod_name}" --force --grace-period=0 >/dev/null
    return 1
}

# =============================================================================
# Funções de Segurança
# =============================================================================

k8s_test_mtls_connectivity() {
    local namespace="$1"
    local source_service="$2"
    local target_service="$3"

    log_info "Testando mTLS entre ${source_service} -> ${target_service}"

    local pod_name="tmp-mtls-test-$(generate_random_string 5)"
    kubectl run "${pod_name}" -n "${namespace}" \
        --image=curlimages/curl --restart=Never \
        --command -- sleep 3600 >/dev/null

    kubectl wait -n "${namespace}" --for=condition=Ready "pod/${pod_name}" --timeout=60s

    if kubectl exec -n "${namespace}" "${pod_name}" -- \
        curl -sSf --connect-timeout 10 \
        "https://${target_service}:443/health" 2>/dev/null; then
        log_success "mTLS connectivity validada"
        kubectl delete pod -n "${namespace}" "${pod_name}" --force --grace-period=0 >/dev/null 2>&1
        return 0
    fi

    log_error "mTLS connectivity falhou"
    kubectl delete pod -n "${namespace}" "${pod_name}" --force --grace-period=0 >/dev/null 2>&1
    return 1
}

k8s_validate_network_policy() {
    local namespace="$1"
    local policy_name="$2"

    log_info "Validando NetworkPolicy ${policy_name} em ${namespace}"

    if ! k8s_resource_exists networkpolicy "${policy_name}" "${namespace}"; then
        log_error "NetworkPolicy ${policy_name} não encontrada"
        return 1
    fi

    local pod_selector
    pod_selector=$(kubectl get networkpolicy -n "${namespace}" "${policy_name}" \
        -o jsonpath='{.spec.podSelector.matchLabels}' 2>/dev/null)

    log_success "NetworkPolicy ${policy_name} validada (selector: ${pod_selector})"
    return 0
}

k8s_check_pod_security_standards() {
    local namespace="$1"

    log_info "Verificando Pod Security Standards em ${namespace}"

    local labels
    labels=$(kubectl get namespace "${namespace}" -o jsonpath='{.metadata.labels}' 2>/dev/null)

    if echo "${labels}" | grep -q "pod-security.kubernetes.io"; then
        local enforce_level
        enforce_level=$(kubectl get namespace "${namespace}" \
            -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}' 2>/dev/null || echo "not-set")
        log_success "Pod Security Standards configurados: ${enforce_level}"
        return 0
    else
        log_warning "Pod Security Standards não configurados em ${namespace}"
        return 1
    fi
}

k8s_verify_service_account_token() {
    local namespace="$1"
    local service_account="$2"

    log_info "Verificando ServiceAccount ${service_account} em ${namespace}"

    if ! kubectl get serviceaccount -n "${namespace}" "${service_account}" >/dev/null 2>&1; then
        log_error "ServiceAccount ${service_account} não encontrada"
        return 1
    fi

    local automount
    automount=$(kubectl get serviceaccount -n "${namespace}" "${service_account}" \
        -o jsonpath='{.automountServiceAccountToken}' 2>/dev/null)

    if [[ "${automount}" == "false" ]]; then
        log_success "ServiceAccount ${service_account} configurada corretamente (automount=false)"
    else
        log_warning "ServiceAccount ${service_account} tem automount habilitado"
    fi

    return 0
}

k8s_list_rbac_bindings() {
    local namespace="${1:-}"

    if [[ -n "${namespace}" ]]; then
        log_info "Listando RoleBindings em ${namespace}"
        kubectl get rolebindings -n "${namespace}" -o wide 2>/dev/null || true
    else
        log_info "Listando ClusterRoleBindings"
        kubectl get clusterrolebindings -o wide 2>/dev/null || true
    fi
}

export -f k8s_namespace_exists k8s_create_namespace k8s_delete_namespace k8s_label_namespace k8s_detect_namespace
export -f k8s_get_pod_name k8s_get_pod_logs k8s_wait_for_pod_ready k8s_exec_in_pod k8s_get_pod_status k8s_get_pods_by_label
export -f k8s_resource_exists k8s_apply_manifest k8s_delete_resource k8s_wait_for_resource k8s_get_resource_status
export -f k8s_port_forward k8s_cleanup_port_forwards k8s_check_port_forward_active
export -f k8s_create_secret k8s_secret_exists k8s_delete_secret
export -f k8s_test_service_connectivity k8s_test_dns_resolution
export -f k8s_test_mtls_connectivity k8s_validate_network_policy k8s_check_pod_security_standards
export -f k8s_verify_service_account_token k8s_list_rbac_bindings
