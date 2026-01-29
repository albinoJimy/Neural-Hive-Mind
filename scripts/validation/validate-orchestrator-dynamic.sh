#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
set -euo pipefail

# Script de validação do Orchestrator Dynamic
# Executa validações completas após deployment

NAMESPACE="${NAMESPACE:-neural-hive-orchestration}"
SERVICE_NAME="orchestrator-dynamic"
TEMPORAL_NAMESPACE="neural-hive-mind"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

VALIDATION_RESULTS=()

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
    VALIDATION_RESULTS+=("PASS: $1")
}

log_fail() {
    echo -e "${RED}[✗]${NC} $1"
    VALIDATION_RESULTS+=("FAIL: $1")
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

validate_deployment() {
    log_info "Validando deployment..."

    # Verificar deployment existe
    if kubectl get deployment "${SERVICE_NAME}" -n "${NAMESPACE}" >/dev/null 2>&1; then
        log_success "Deployment existe"
    else
        log_fail "Deployment não encontrado"
        return 1
    fi

    # Verificar réplicas
    DESIRED=$(kubectl get deployment "${SERVICE_NAME}" -n "${NAMESPACE}" -o jsonpath='{.spec.replicas}')
    READY=$(kubectl get deployment "${SERVICE_NAME}" -n "${NAMESPACE}" -o jsonpath='{.status.readyReplicas}')

    if [ "${READY}" = "${DESIRED}" ]; then
        log_success "Réplicas ready: ${READY}/${DESIRED}"
    else
        log_fail "Réplicas não ready: ${READY}/${DESIRED}"
        return 1
    fi

    # Verificar pods running
    PODS=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${SERVICE_NAME}" -o jsonpath='{.items[*].status.phase}')
    if echo "${PODS}" | grep -q Running; then
        log_success "Pods em estado Running"
    else
        log_fail "Pods não estão Running: ${PODS}"
        return 1
    fi

    # Verificar restart loops
    MAX_RESTARTS=3
    RESTART_COUNT=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${SERVICE_NAME}" -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}')
    if [ "${RESTART_COUNT}" -lt "${MAX_RESTARTS}" ]; then
        log_success "Restart count OK: ${RESTART_COUNT}"
    else
        log_warn "Restart count alto: ${RESTART_COUNT}"
    fi
}

validate_service() {
    log_info "Validando service..."

    # Verificar service existe
    if kubectl get service "${SERVICE_NAME}" -n "${NAMESPACE}" >/dev/null 2>&1; then
        log_success "Service existe"
    else
        log_fail "Service não encontrado"
        return 1
    fi

    # Verificar endpoints
    ENDPOINTS=$(kubectl get endpoints "${SERVICE_NAME}" -n "${NAMESPACE}" -o jsonpath='{.subsets[*].addresses[*].ip}' | wc -w)
    if [ "${ENDPOINTS}" -gt 0 ]; then
        log_success "Endpoints disponíveis: ${ENDPOINTS}"
    else
        log_fail "Nenhum endpoint disponível"
        return 1
    fi

    # Verificar ClusterIP
    CLUSTER_IP=$(kubectl get service "${SERVICE_NAME}" -n "${NAMESPACE}" -o jsonpath='{.spec.clusterIP}')
    if [ "${CLUSTER_IP}" != "None" ] && [ -n "${CLUSTER_IP}" ]; then
        log_success "ClusterIP atribuído: ${CLUSTER_IP}"
    else
        log_fail "ClusterIP não atribuído"
        return 1
    fi
}

validate_health_endpoints() {
    log_info "Validando health endpoints..."

    POD_NAME=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${SERVICE_NAME}" -o jsonpath='{.items[0].metadata.name}')

    # Test /health
    if kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        log_success "Endpoint /health respondendo"
    else
        log_fail "Endpoint /health não respondendo"
        return 1
    fi

    # Test /ready
    if kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- curl -sf http://localhost:8000/ready >/dev/null 2>&1; then
        log_success "Endpoint /ready respondendo"
    else
        log_fail "Endpoint /ready não respondendo"
        return 1
    fi

    # Verificar resposta JSON
    HEALTH_RESPONSE=$(kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- curl -s http://localhost:8000/health)
    if echo "${HEALTH_RESPONSE}" | grep -q "status"; then
        log_success "Resposta JSON válida"
    else
        log_fail "Resposta JSON inválida"
    fi
}

validate_temporal_connection() {
    log_info "Validando conexão com Temporal..."

    # Verificar Temporal Server acessível
    if kubectl get service -n temporal temporal-frontend >/dev/null 2>&1; then
        log_success "Temporal Server encontrado"
    else
        log_fail "Temporal Server não encontrado"
        return 1
    fi

    # Verificar logs do orchestrator mencionam Temporal
    POD_NAME=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${SERVICE_NAME}" -o jsonpath='{.items[0].metadata.name}')
    if kubectl logs -n "${NAMESPACE}" "${POD_NAME}" --tail=100 | grep -qi "temporal"; then
        log_success "Logs mencionam Temporal"
    else
        log_warn "Logs não mencionam Temporal"
    fi
}

validate_kafka_integration() {
    log_info "Validando integração com Kafka..."

    # Verificar consumer group
    KAFKA_POD=$(kubectl get pods -n kafka -l app.kubernetes.io/name=kafka -o jsonpath='{.items[0].metadata.name}')

    if kubectl exec -n kafka "${KAFKA_POD}" -- kafka-consumer-groups.sh \
        --bootstrap-server localhost:9092 \
        --describe \
        --group orchestrator-dynamic 2>/dev/null | grep -q orchestrator-dynamic; then
        log_success "Consumer group existe"
    else
        log_warn "Consumer group não encontrado (pode não ter iniciado consumo ainda)"
    fi

    # Verificar tópicos existem
    TOPICS=("plans.consensus" "execution.tickets" "orchestration.incidents" "telemetry.orchestration")
    for topic in "${TOPICS[@]}"; do
        if kubectl exec -n kafka "${KAFKA_POD}" -- kafka-topics.sh \
            --bootstrap-server localhost:9092 \
            --list 2>/dev/null | grep -q "${topic}"; then
            log_success "Tópico ${topic} existe"
        else
            log_fail "Tópico ${topic} não existe"
        fi
    done
}

validate_observability() {
    log_info "Validando observabilidade..."

    POD_NAME=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${SERVICE_NAME}" -o jsonpath='{.items[0].metadata.name}')

    # Verificar métricas Prometheus
    if kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- curl -s http://localhost:9090/metrics | grep -q "orchestration_"; then
        log_success "Métricas Prometheus sendo exportadas"
    else
        log_fail "Métricas Prometheus não encontradas"
        return 1
    fi

    # Verificar ServiceMonitor
    if kubectl get servicemonitor -n "${NAMESPACE}" "${SERVICE_NAME}" >/dev/null 2>&1; then
        log_success "ServiceMonitor existe"
    else
        log_warn "ServiceMonitor não encontrado"
    fi

    # Verificar annotations Prometheus
    POD_ANNOTATIONS=$(kubectl get pod -n "${NAMESPACE}" "${POD_NAME}" -o jsonpath='{.metadata.annotations}')
    if echo "${POD_ANNOTATIONS}" | grep -q "prometheus.io/scrape"; then
        log_success "Annotations Prometheus configuradas"
    else
        log_warn "Annotations Prometheus ausentes"
    fi
}

validate_istio_integration() {
    log_info "Validando integração com Istio..."

    POD_NAME=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${SERVICE_NAME}" -o jsonpath='{.items[0].metadata.name}')

    # Verificar sidecar Istio
    CONTAINERS=$(kubectl get pod -n "${NAMESPACE}" "${POD_NAME}" -o jsonpath='{.spec.containers[*].name}')
    if echo "${CONTAINERS}" | grep -q "istio-proxy"; then
        log_success "Sidecar Istio injetado"
    else
        log_warn "Sidecar Istio não encontrado"
    fi

    # Verificar mTLS
    if command -v istioctl >/dev/null 2>&1; then
        if istioctl authn tls-check -n "${NAMESPACE}" "${POD_NAME}" 2>/dev/null | grep -q "mTLS"; then
            log_success "mTLS ativo"
        else
            log_warn "mTLS não verificado"
        fi
    fi
}

generate_report() {
    log_info ""
    log_info "===== Relatório de Validação ====="
    log_info ""

    PASS_COUNT=0
    FAIL_COUNT=0

    for result in "${VALIDATION_RESULTS[@]}"; do
        if [[ "${result}" == PASS* ]]; then
            echo -e "${GREEN}${result}${NC}"
            ((PASS_COUNT++))
        else
            echo -e "${RED}${result}${NC}"
            ((FAIL_COUNT++))
        fi
    done

    log_info ""
    log_info "Total: ${PASS_COUNT} passou, ${FAIL_COUNT} falhou"
    log_info ""

    if [ "${FAIL_COUNT}" -eq 0 ]; then
        log_success "Todas as validações passaram!"
        return 0
    else
        log_fail "Algumas validações falharam"
        return 1
    fi
}

main() {
    log_info "===== Validação Orchestrator Dynamic ====="
    log_info "Namespace: ${NAMESPACE}"
    log_info "==========================================="
    log_info ""

    validate_deployment || true
    validate_service || true
    validate_health_endpoints || true
    validate_temporal_connection || true
    validate_kafka_integration || true
    validate_observability || true
    validate_istio_integration || true

    generate_report
}

main "$@"
