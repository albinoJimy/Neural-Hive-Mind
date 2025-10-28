#!/bin/bash

###############################################################################
# Validation Script - Execution Ticket Service
# Valida deployment e saúde do Execution Ticket Service
###############################################################################

set -e

NAMESPACE="${NAMESPACE:-neural-hive-orchestration}"
SERVICE_NAME="execution-ticket-service"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASSED=0
FAILED=0

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED++))
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

## 1. Deployment e Pods
validate_deployment() {
    log_info "Validando deployment e pods..."

    if kubectl get deployment $SERVICE_NAME -n $NAMESPACE >/dev/null 2>&1; then
        log_pass "Deployment existe"
    else
        log_fail "Deployment não encontrado"
        return
    fi

    REPLICAS=$(kubectl get deployment $SERVICE_NAME -n $NAMESPACE -o jsonpath='{.status.replicas}')
    READY=$(kubectl get deployment $SERVICE_NAME -n $NAMESPACE -o jsonpath='{.status.readyReplicas}')

    if [ "$REPLICAS" == "$READY" ] && [ "$READY" -gt 0 ]; then
        log_pass "Pods prontos: $READY/$REPLICAS"
    else
        log_fail "Pods não prontos: $READY/$REPLICAS"
    fi

    RESTARTS=$(kubectl get pods -n $NAMESPACE -l app=$SERVICE_NAME -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}')
    if [ "$RESTARTS" -lt 3 ]; then
        log_pass "Restarts OK: $RESTARTS"
    else
        log_warn "Muitos restarts: $RESTARTS"
    fi
}

## 2. Service e Endpoints
validate_service() {
    log_info "Validando service..."

    if kubectl get service $SERVICE_NAME -n $NAMESPACE >/dev/null 2>&1; then
        log_pass "Service existe"
    else
        log_fail "Service não encontrado"
        return
    fi

    ENDPOINTS=$(kubectl get endpoints $SERVICE_NAME -n $NAMESPACE -o jsonpath='{.subsets[0].addresses}' | wc -w)
    if [ "$ENDPOINTS" -gt 0 ]; then
        log_pass "Service tem $ENDPOINTS endpoints"
    else
        log_fail "Service sem endpoints"
    fi
}

## 3. Health Checks
validate_health() {
    log_info "Validando health checks..."

    PODNAME=$(kubectl get pods -n $NAMESPACE -l app=$SERVICE_NAME -o jsonpath='{.items[0].metadata.name}')

    if kubectl exec $PODNAME -n $NAMESPACE -- curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        log_pass "Health endpoint OK"
    else
        log_fail "Health endpoint falhou"
    fi

    if kubectl exec $PODNAME -n $NAMESPACE -- curl -sf http://localhost:8000/ready >/dev/null 2>&1; then
        log_pass "Ready endpoint OK"
    else
        log_warn "Ready endpoint não está pronto (dependências podem estar indisponíveis)"
    fi
}

## 4. Métricas
validate_metrics() {
    log_info "Validando métricas..."

    PODNAME=$(kubectl get pods -n $NAMESPACE -l app=$SERVICE_NAME -o jsonpath='{.items[0].metadata.name}')

    if kubectl exec $PODNAME -n $NAMESPACE -- curl -sf http://localhost:9090/metrics >/dev/null 2>&1; then
        log_pass "Metrics endpoint OK"
    else
        log_fail "Metrics endpoint falhou"
    fi

    # Verificar métricas específicas
    METRICS=$(kubectl exec $PODNAME -n $NAMESPACE -- curl -s http://localhost:9090/metrics 2>/dev/null)

    if echo "$METRICS" | grep -q "tickets_consumed_total"; then
        log_pass "Métrica tickets_consumed_total presente"
    else
        log_warn "Métrica tickets_consumed_total não encontrada"
    fi
}

## 5. Logs
validate_logs() {
    log_info "Validando logs..."

    PODNAME=$(kubectl get pods -n $NAMESPACE -l app=$SERVICE_NAME -o jsonpath='{.items[0].metadata.name}')
    LOGS=$(kubectl logs $PODNAME -n $NAMESPACE --tail=50 2>/dev/null)

    if echo "$LOGS" | grep -q "Service startup complete"; then
        log_pass "Service inicializado com sucesso"
    else
        log_fail "Service não inicializou corretamente"
    fi

    if echo "$LOGS" | grep -qi "error"; then
        log_warn "Erros encontrados nos logs (verificar manualmente)"
    fi
}

## 6. API REST
validate_api() {
    log_info "Validando API REST..."

    PODNAME=$(kubectl get pods -n $NAMESPACE -l app=$SERVICE_NAME -o jsonpath='{.items[0].metadata.name}')

    # Testar endpoint de listagem (deve retornar array vazio ou tickets)
    if kubectl exec $PODNAME -n $NAMESPACE -- curl -sf http://localhost:8000/api/v1/tickets?limit=1 >/dev/null 2>&1; then
        log_pass "API endpoint /api/v1/tickets OK"
    else
        log_warn "API endpoint /api/v1/tickets não disponível (pode ser esperado se DB não estiver configurado)"
    fi
}

## 7. Configuração
validate_config() {
    log_info "Validando configuração..."

    if kubectl get secret execution-ticket-service-secrets -n $NAMESPACE >/dev/null 2>&1; then
        log_pass "Secret existe"
    else
        log_fail "Secret não encontrado"
    fi

    if kubectl get configmap -n $NAMESPACE 2>/dev/null | grep -q $SERVICE_NAME; then
        log_pass "ConfigMap existe"
    else
        log_warn "ConfigMap não encontrado (pode usar apenas secrets)"
    fi
}

## 8. Recursos
validate_resources() {
    log_info "Validando recursos..."

    PODNAME=$(kubectl get pods -n $NAMESPACE -l app=$SERVICE_NAME -o jsonpath='{.items[0].metadata.name}')

    CPU=$(kubectl top pod $PODNAME -n $NAMESPACE 2>/dev/null | tail -1 | awk '{print $2}')
    MEM=$(kubectl top pod $PODNAME -n $NAMESPACE 2>/dev/null | tail -1 | awk '{print $3}')

    if [ ! -z "$CPU" ]; then
        log_pass "CPU usage: $CPU"
        log_pass "Memory usage: $MEM"
    else
        log_warn "Métricas de recursos não disponíveis (metrics-server pode não estar instalado)"
    fi
}

## Main
main() {
    log_info "===== Validação Execution Ticket Service ====="
    log_info "Namespace: $NAMESPACE"
    echo

    validate_deployment
    echo
    validate_service
    echo
    validate_health
    echo
    validate_metrics
    echo
    validate_logs
    echo
    validate_api
    echo
    validate_config
    echo
    validate_resources
    echo

    log_info "===== Resumo ====="
    echo -e "${GREEN}Passed: $PASSED${NC}"
    echo -e "${RED}Failed: $FAILED${NC}"

    if [ $FAILED -eq 0 ]; then
        log_info "✅ Todas as validações passaram!"
        exit 0
    else
        log_warn "⚠️  Algumas validações falharam. Verificar logs detalhados."
        exit 1
    fi
}

main "$@"
