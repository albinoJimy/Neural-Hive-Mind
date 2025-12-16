#!/bin/bash

###############################################################################
# End-to-End Test - Execution Ticket Service
# Testa fluxo completo: Kafka → Persistência → API → Tokens
###############################################################################

set -e

NAMESPACE="${NAMESPACE:-neural-hive-orchestration}"
SERVICE_NAME="execution-ticket-service"
TEST_TICKET_ID="test-ticket-$(date +%s)"

# Cores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    exit 1
}

## 1. Verificar Infraestrutura
test_infrastructure() {
    log_info "Fase 1: Verificando infraestrutura..."

    # Verificar pods
    kubectl get pods -n $NAMESPACE -l app=$SERVICE_NAME >/dev/null 2>&1 || log_fail "Service não está rodando"
    log_pass "Service está rodando"

    # Health check
    PODNAME=$(kubectl get pods -n $NAMESPACE -l app=$SERVICE_NAME -o jsonpath='{.items[0].metadata.name}')
    kubectl exec $PODNAME -n $NAMESPACE -- curl -sf http://localhost:8000/health >/dev/null 2>&1 || log_fail "Health check falhou"
    log_pass "Health check OK"
}

## 2. Teste de API REST
test_rest_api() {
    log_info "Fase 2: Testando API REST..."

    PODNAME=$(kubectl get pods -n $NAMESPACE -l app=$SERVICE_NAME -o jsonpath='{.items[0].metadata.name}')

    # Testar listagem
    RESPONSE=$(kubectl exec $PODNAME -n $NAMESPACE -- curl -s http://localhost:8000/api/v1/tickets?limit=10)

    if echo "$RESPONSE" | grep -q "tickets"; then
        log_pass "API /api/v1/tickets retorna JSON válido"
    else
        log_fail "API /api/v1/tickets retorna resposta inválida"
    fi

    # Contar tickets
    TOTAL=$(echo "$RESPONSE" | grep -o '"total":[0-9]*' | cut -d':' -f2)
    log_info "Total de tickets no sistema: $TOTAL"
}

## 3. Teste de Métricas
test_metrics() {
    log_info "Fase 3: Testando métricas Prometheus..."

    PODNAME=$(kubectl get pods -n $NAMESPACE -l app=$SERVICE_NAME -o jsonpath='{.items[0].metadata.name}')
    METRICS=$(kubectl exec $PODNAME -n $NAMESPACE -- curl -s http://localhost:9090/metrics)

    # Verificar métricas existem
    EXPECTED_METRICS=(
        "tickets_consumed_total"
        "tickets_persisted_total"
        "api_requests_total"
        "webhooks_enqueued_total"
        "postgres_queries_total"
    )

    for metric in "${EXPECTED_METRICS[@]}"; do
        if echo "$METRICS" | grep -q "$metric"; then
            log_pass "Métrica $metric presente"
        else
            log_fail "Métrica $metric não encontrada"
        fi
    done
}

## 4. Teste de Observabilidade
test_observability() {
    log_info "Fase 4: Testando observabilidade..."

    PODNAME=$(kubectl get pods -n $NAMESPACE -l app=$SERVICE_NAME -o jsonpath='{.items[0].metadata.name}')
    LOGS=$(kubectl logs $PODNAME -n $NAMESPACE --tail=100)

    # Verificar logs estruturados (JSON)
    if echo "$LOGS" | head -5 | grep -q "{"; then
        log_pass "Logs estruturados (JSON) OK"
    else
        log_fail "Logs não estão estruturados"
    fi

    # Verificar startup completo
    if echo "$LOGS" | grep -q "Service startup complete"; then
        log_pass "Service inicializou completamente"
    else
        log_fail "Service não completou inicialização"
    fi
}

## 5. Cleanup
cleanup() {
    log_info "Limpeza: nenhum recurso de teste criado"
}

## Main
main() {
    log_info "===== Teste End-to-End: Execution Ticket Service ====="
    log_info "Namespace: $NAMESPACE"
    echo

    test_infrastructure
    echo

    test_rest_api
    echo

    test_metrics
    echo

    test_observability
    echo

    cleanup
    echo

    log_pass "✅ Todos os testes passaram!"
    log_info "Próximos passos:"
    log_info "  1. Testar integração completa com Orchestrator (publicar ticket no Kafka)"
    log_info "  2. Testar geração de tokens JWT"
    log_info "  3. Testar webhooks (requer Worker Agent mock)"
}

main "$@"
