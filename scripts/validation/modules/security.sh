#!/bin/bash

validate_security() {
    log_info "=== Validando Segurança ==="
    
    local namespace="${NAMESPACE:-security}"
    
    validate_opa "$namespace"
    validate_mtls "$namespace"
    validate_oauth "$namespace"
    validate_namespace_isolation "$namespace"
    validate_sigstore "$namespace"
}

validate_opa() {
    local namespace="$1"
    log_info "Validando OPA policies..."
    
    if check_pod_running "opa" "$namespace"; then
        add_test_result "opa_status" "PASS" "high" "OPA pod Running" "" "3"
    else
        add_test_result "opa_status" "FAIL" "high" "OPA pod não Running" "" "3"
    fi
}

validate_mtls() {
    local namespace="$1"
    log_info "Validando mTLS..."
    
    add_test_result "mtls_connectivity" "SKIP" "high" "Teste de mTLS consolidado, não executado automaticamente" "" "0"
}

validate_oauth() {
    local namespace="$1"
    log_info "Validando OAuth2..."
    
    if check_pod_running "keycloak" "$namespace"; then
        add_test_result "oauth2_flow" "PASS" "medium" "Keycloak disponível" "" "2"
    else
        add_test_result "oauth2_flow" "WARNING" "medium" "Keycloak indisponível" "" "2"
    fi
}

validate_namespace_isolation() {
    local namespace="$1"
    log_info "Validando isolamento de namespaces..."
    
    add_test_result "namespace_isolation" "SKIP" "medium" "Validação de isolamento não automatizada" "" "0"
}

validate_sigstore() {
    local namespace="$1"
    log_info "Validando assinatura Sigstore..."
    
    add_test_result "sigstore_verification" "SKIP" "medium" "Validação Sigstore consolidada, não executada" "" "0"
}
