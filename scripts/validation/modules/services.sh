#!/bin/bash

validate_services() {
    log_info "=== Validando Serviços ==="
    
    local namespace="${NAMESPACE:-neural-hive-services}"
    local components=(
        "gateway"
        "consensus-engine"
        "memory-layer"
        "semantic-translation-engine"
        "orchestrator"
        "execution-ticket-service"
        "worker-agents"
        "queen-agent"
        "scout-agents"
        "guard-agents"
        "service-registry"
        "sla-management-system"
        "mcp-tool-catalog"
    )
    
    if [[ -n "$COMPONENT" ]]; then
        validate_service_component "$COMPONENT" "$namespace"
        return
    fi
    
    for component in "${components[@]}"; do
        validate_service_component "$component" "$namespace"
    done
}

validate_service_component() {
    local component="$1"
    local namespace="$2"
    
    log_info "Validando serviço: $component"
    
    local test_name="${component}_pod_status"
    if check_pod_running "$component" "$namespace"; then
        add_test_result "$test_name" "PASS" "high" "Pod Running" "" "2"
    else
        add_test_result "$test_name" "FAIL" "high" "Pod não Running" "" "2"
    fi
}
