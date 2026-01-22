#!/bin/bash

validate_specialists() {
    log_info "=== Validando Specialists ==="

    # Se componente específico foi especificado
    if [[ -n "$COMPONENT" ]]; then
        validate_single_specialist "$COMPONENT"
        return
    fi

    # Specialists disponíveis (não mapeiam 1:1 com os 7 domínios unificados)
    # Domínios Unificados: BUSINESS, TECHNICAL, SECURITY, INFRASTRUCTURE, BEHAVIOR, OPERATIONAL, COMPLIANCE
    # Specialists são componentes de serviço que podem processar múltiplos domínios
    # - business specialist: processa domínio BUSINESS
    # - technical specialist: processa domínios TECHNICAL, SECURITY
    # - behavior specialist: processa domínio BEHAVIOR
    # - evolution specialist: processa domínios OPERATIONAL, COMPLIANCE
    # - architecture specialist: processa domínio INFRASTRUCTURE
    local specialists=("business" "technical" "behavior" "evolution" "architecture")
    
    for specialist in "${specialists[@]}"; do
        validate_single_specialist "$specialist"
    done
    
    # Validar modelos ML
    if [[ "$QUICK_MODE" == false ]]; then
        validate_ml_models
        validate_inference
    fi
}

validate_single_specialist() {
    local specialist="$1"
    local namespace="${NAMESPACE:-neural-hive-specialists}"
    local service="specialist-${specialist}"
    
    log_info "Validando specialist: $specialist"
    
    # 1. Pod Status
    local test_name="${specialist}_pod_status"
    if check_pod_running "$service" "$namespace"; then
        add_test_result "$test_name" "PASS" "high" "Pod está Running" "" "2"
    else
        add_test_result "$test_name" "FAIL" "high" "Pod não está Running" "Verificar logs: kubectl logs -l app.kubernetes.io/name=$service -n $namespace" "2"
    fi
    
    # 2. Health Endpoint
    test_name="${specialist}_health_endpoint"
    if check_http_endpoint "$service" "$namespace" "/health"; then
        add_test_result "$test_name" "PASS" "critical" "Health endpoint respondendo" "" "3"
    else
        add_test_result "$test_name" "FAIL" "critical" "Health endpoint não responde" "Verificar configuração do serviço" "3"
    fi
    
    # 3. gRPC Endpoint
    test_name="${specialist}_grpc_endpoint"
    if check_grpc_endpoint "$service" "$namespace" "50051"; then
        add_test_result "$test_name" "PASS" "critical" "gRPC endpoint acessível" "" "2"
    else
        add_test_result "$test_name" "FAIL" "critical" "gRPC endpoint não acessível" "Verificar porta 50051" "2"
    fi
    
    # 4. MongoDB Connectivity
    test_name="${specialist}_mongodb_connectivity"
    if check_dependency_connectivity "$service" "$namespace" "mongodb.mongodb-cluster.svc.cluster.local" "27017"; then
        add_test_result "$test_name" "PASS" "high" "MongoDB acessível" "" "2"
    else
        add_test_result "$test_name" "FAIL" "high" "MongoDB não acessível" "Verificar serviço MongoDB" "2"
    fi
    
    # 5. Model Loaded
    test_name="${specialist}_model_loaded"
    if check_model_loaded "$service" "$namespace"; then
        add_test_result "$test_name" "PASS" "critical" "Modelo ML carregado" "" "3"
    else
        add_test_result "$test_name" "FAIL" "critical" "Modelo ML não carregado" "Verificar MLflow e logs" "3"
    fi
    
    # 6. Metrics Endpoint
    test_name="${specialist}_metrics_endpoint"
    if check_metrics_endpoint "$service" "$namespace"; then
        add_test_result "$test_name" "PASS" "medium" "Métricas Prometheus disponíveis" "" "2"
    else
        add_test_result "$test_name" "WARNING" "medium" "Métricas não disponíveis" "Verificar porta 8080/metrics" "2"
    fi
}

validate_ml_models() {
    log_info "Validando modelos ML no MLflow..."
    
    # Executar script de validação de modelos
    local models_script="${SCRIPT_DIR}/../ml_pipelines/training/validate_models_loaded.sh"
    
    if [[ -f "$models_script" ]]; then
        if bash "$models_script" > /dev/null 2>&1; then
            add_test_result "ml_models_validation" "PASS" "high" "Modelos ML validados no MLflow" "" "5"
        else
            add_test_result "ml_models_validation" "FAIL" "high" "Falha na validação de modelos ML" "Verificar MLflow" "5"
        fi
    else
        add_test_result "ml_models_validation" "SKIP" "high" "Script de validação não encontrado" "" "0"
    fi
}

validate_inference() {
    log_info "Testando inferência de modelos..."
    
    local inference_script="${SCRIPT_DIR}/validation/test-specialist-inference.py"
    
    if [[ -f "$inference_script" ]]; then
        if python3 "$inference_script" --namespace "${NAMESPACE:-neural-hive-specialists}" > /dev/null 2>&1; then
            add_test_result "inference_test" "PASS" "high" "Teste de inferência passou" "" "10"
        else
            add_test_result "inference_test" "FAIL" "high" "Teste de inferência falhou" "Verificar modelos e endpoints gRPC" "10"
        fi
    else
        add_test_result "inference_test" "SKIP" "high" "Script de teste não encontrado" "" "0"
    fi
}

# Funções auxiliares
check_model_loaded() {
    local service="$1"
    local namespace="$2"
    
    local pod=$(kubectl get pods -n "$namespace" -l "app.kubernetes.io/name=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [[ -z "$pod" ]]; then
        return 1
    fi
    
    # Port-forward e testar /status endpoint
    kubectl port-forward "$pod" -n "$namespace" 8000:8000 > /dev/null 2>&1 &
    local pf_pid=$!
    sleep 2
    
    local status=$(curl -s http://localhost:8000/status 2>/dev/null | jq -r '.details.model_loaded // "false"')
    
    kill $pf_pid 2>/dev/null || true
    wait $pf_pid 2>/dev/null || true
    
    [[ "$status" == "true" || "$status" == "True" ]]
}

check_metrics_endpoint() {
    local service="$1"
    local namespace="$2"
    
    local pod=$(kubectl get pods -n "$namespace" -l "app.kubernetes.io/name=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [[ -z "$pod" ]]; then
        return 1
    fi
    
    kubectl port-forward "$pod" -n "$namespace" 8080:8080 > /dev/null 2>&1 &
    local pf_pid=$!
    sleep 2
    
    local metrics=$(curl -s http://localhost:8080/metrics 2>/dev/null | grep -c "# HELP" || echo "0")
    
    kill $pf_pid 2>/dev/null || true
    wait $pf_pid 2>/dev/null || true
    
    [[ "$metrics" -gt 0 ]]
}
