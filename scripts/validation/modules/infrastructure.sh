#!/bin/bash

validate_infrastructure() {
    log_info "=== Validando Infraestrutura ==="
    
    local namespace="${NAMESPACE:-infrastructure}"
    
    validate_k8s_cluster
    validate_kafka "$namespace"
    validate_redis "$namespace"
    validate_mongodb "$namespace"
    validate_neo4j "$namespace"
    validate_clickhouse "$namespace"
    validate_keycloak "$namespace"
}

validate_k8s_cluster() {
    log_info "Verificando saúde do cluster Kubernetes..."
    
    local nodes_status
    nodes_status=$(kubectl get nodes --no-headers 2>/dev/null | awk '{print $2}' | grep -cv Ready || echo "0")
    
    if [[ "$nodes_status" -eq 0 ]]; then
        add_test_result "k8s_cluster" "PASS" "critical" "Todos os nós Ready" "" "5"
    else
        add_test_result "k8s_cluster" "FAIL" "critical" "$nodes_status nós não estão Ready" "kubectl get nodes" "5"
    fi
}

validate_kafka() {
    local namespace="$1"
    log_info "Validando Kafka..."
    
    if check_pod_running "kafka" "$namespace"; then
        add_test_result "kafka_status" "PASS" "high" "Kafka pod Running" "" "3"
    else
        add_test_result "kafka_status" "FAIL" "high" "Kafka pod não Running" "" "3"
    fi
}

validate_redis() {
    local namespace="$1"
    log_info "Validando Redis..."
    
    if check_pod_running "redis" "$namespace"; then
        add_test_result "redis_status" "PASS" "high" "Redis pod Running" "" "3"
    else
        add_test_result "redis_status" "FAIL" "high" "Redis pod não Running" "" "3"
    fi
}

validate_mongodb() {
    local namespace="$1"
    log_info "Validando MongoDB..."
    
    if check_pod_running "mongodb" "$namespace"; then
        add_test_result "mongodb_status" "PASS" "high" "MongoDB pod Running" "" "3"
    else
        add_test_result "mongodb_status" "FAIL" "high" "MongoDB pod não Running" "" "3"
    fi
}

validate_neo4j() {
    local namespace="$1"
    log_info "Validando Neo4j..."
    
    if check_pod_running "neo4j" "$namespace"; then
        add_test_result "neo4j_status" "PASS" "medium" "Neo4j pod Running" "" "2"
    else
        add_test_result "neo4j_status" "FAIL" "medium" "Neo4j pod não Running" "" "2"
    fi
}

validate_clickhouse() {
    local namespace="$1"
    log_info "Validando ClickHouse..."
    
    if check_pod_running "clickhouse" "$namespace"; then
        add_test_result "clickhouse_status" "PASS" "medium" "ClickHouse pod Running" "" "2"
    else
        add_test_result "clickhouse_status" "FAIL" "medium" "ClickHouse pod não Running" "" "2"
    fi
}

validate_keycloak() {
    local namespace="$1"
    log_info "Validando Keycloak..."
    
    if check_pod_running "keycloak" "$namespace"; then
        add_test_result "keycloak_status" "PASS" "medium" "Keycloak pod Running" "" "2"
    else
        add_test_result "keycloak_status" "FAIL" "medium" "Keycloak pod não Running" "" "2"
    fi
}
