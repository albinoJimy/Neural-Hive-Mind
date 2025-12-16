#!/usr/bin/env bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
#
# Validate Phase 2 Flow C Integration
#
# Este script valida o deployment completo da integração Flow C (Fase 2):
# - Verifica pods/rollouts de todos os serviços
# - Testa conectividade entre serviços
# - Valida Kafka topics e consumer groups
# - Verifica workers registrados no Service Registry
# - Confirma métricas Prometheus e spans Jaeger
# - Verifica Grafana dashboard e alertas
#

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variáveis
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NAMESPACE="${NAMESPACE:-neural-hive-orchestration}"
ORCH_NAMESPACE="${ORCH_NAMESPACE:-$NAMESPACE}"
SERVICE_REGISTRY_NAMESPACE="${SERVICE_REGISTRY_NAMESPACE:-neural-hive-service-registry}"
WORKERS_NAMESPACE="${WORKERS_NAMESPACE:-neural-hive-workers}"
CODE_FORGE_NAMESPACE="${CODE_FORGE_NAMESPACE:-neural-hive-code-forge}"
KAFKA_NAMESPACE="${KAFKA_NAMESPACE:-neural-hive-kafka}"
KAFKA_CLUSTER="${KAFKA_CLUSTER:-neural-hive-kafka}"
MONITORING_NAMESPACE="${MONITORING_NAMESPACE:-neural-hive-observability}"
VERBOSE=false

# Contadores
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNED=0

# Logging
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $*"
    ((CHECKS_PASSED++))
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
    ((CHECKS_WARNED++))
}

log_error() {
    echo -e "${RED}[✗]${NC} $*"
    ((CHECKS_FAILED++))
}

# Parse argumentos
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --verbose)
                VERBOSE=true
                set -x
                shift
                ;;
            --namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            -h|--help)
                cat <<EOF
Uso: $0 [OPTIONS]

Opções:
  --verbose          Ativa modo verbose (set -x)
  --namespace NS     Define namespace k8s (default: neural-hive-orchestration)
  -h, --help         Exibe esta mensagem

Exemplos:
  $0                    # Validação padrão
  $0 --verbose          # Validação com output verbose
EOF
                exit 0
                ;;
            *)
                log_error "Argumento desconhecido: $1"
                exit 1
                ;;
        esac
    done
}

# Verificar pods e rollouts
check_pods_and_rollouts() {
    log_info "=== Verificando Pods e Rollouts ==="

    local services=(
        "orchestrator-dynamic:${ORCH_NAMESPACE}"
        "service-registry:${SERVICE_REGISTRY_NAMESPACE}"
        "execution-ticket-service:${ORCH_NAMESPACE}"
        "worker-agents:${WORKERS_NAMESPACE}"
        "code-forge:${CODE_FORGE_NAMESPACE}"
    )

    for service_ns in "${services[@]}"; do
        IFS=':' read -r service namespace <<<"$service_ns"
        log_info "Verificando: $service (ns=$namespace)"

        # Verificar pods
        local pods
        pods=$(kubectl get pods -n "$namespace" -l app.kubernetes.io/name="$service" --no-headers 2>/dev/null | wc -l)
        if [ "$pods" -eq 0 ]; then
            pods=$(kubectl get pods -n "$namespace" -l app="$service" --no-headers 2>/dev/null | wc -l)
        fi
        if [ "$pods" -gt 0 ]; then
            local ready
            ready=$(kubectl get pods -n "$namespace" -l app.kubernetes.io/name="$service" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
            if [ "$ready" -eq 0 ]; then
                ready=$(kubectl get pods -n "$namespace" -l app="$service" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
            fi
            if [ "$ready" -eq "$pods" ]; then
                log_success "$service: $ready/$pods pods running"
            else
                log_warn "$service: apenas $ready/$pods pods running"
            fi
        else
            log_error "$service: nenhum pod encontrado"
        fi

        # Verificar health endpoint
        local pod
        pod=$(kubectl get pods -n "$namespace" -l app.kubernetes.io/name="$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
        if [ -z "$pod" ]; then
            pod=$(kubectl get pods -n "$namespace" -l app="$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
        fi
        if [ -n "$pod" ]; then
            if kubectl exec -n "$namespace" "$pod" -- wget -q -O- http://localhost:8080/health 2>/dev/null | grep -q "ok\|healthy\|UP" || \
               kubectl exec -n "$namespace" "$pod" -- wget -q -O- http://localhost:8080/healthz 2>/dev/null | grep -q "ok\|healthy\|UP"; then
                log_success "$service: health endpoint OK"
            else
                log_warn "$service: health endpoint não respondeu como esperado"
            fi
        fi
    done

    echo
}

# Verificar conectividade entre serviços
check_service_connectivity() {
    log_info "=== Verificando Conectividade entre Serviços ==="

    # Orchestrator -> Service Registry
    log_info "Testando: orchestrator-dynamic -> service-registry"
    local orch_pod
    orch_pod=$(kubectl get pods -n "$ORCH_NAMESPACE" -l app.kubernetes.io/name=orchestrator-dynamic -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$orch_pod" ]; then
        if kubectl exec -n "$ORCH_NAMESPACE" "$orch_pod" -- nc -zv "service-registry.${SERVICE_REGISTRY_NAMESPACE}.svc.cluster.local" 50051 2>&1 | grep -q "succeeded\|open"; then
            log_success "orchestrator-dynamic -> service-registry: conectividade OK"
        else
            log_warn "orchestrator-dynamic -> service-registry: conectividade falhou"
        fi
    else
        log_warn "Pod orchestrator-dynamic não encontrado para teste de conectividade"
    fi

    # Worker -> Execution Ticket Service
    log_info "Testando: worker-agents -> execution-ticket-service"
    local worker_pod
    worker_pod=$(kubectl get pods -n "$WORKERS_NAMESPACE" -l app.kubernetes.io/name=worker-agents -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$worker_pod" ]; then
        if kubectl exec -n "$WORKERS_NAMESPACE" "$worker_pod" -- nc -zv "execution-ticket-service.${ORCH_NAMESPACE}.svc.cluster.local" 8000 2>&1 | grep -q "succeeded\|open"; then
            log_success "worker-agents -> execution-ticket-service: conectividade OK"
        else
            log_warn "worker-agents -> execution-ticket-service: conectividade falhou"
        fi
    else
        log_warn "Pod worker-agents não encontrado para teste de conectividade"
    fi

    echo
}

# Verificar Kafka topics e consumer groups
check_kafka_topics() {
    log_info "=== Verificando Kafka Topics e Consumer Groups ==="

    local topics=(
        "plans.consensus"
        "execution.tickets"
        "telemetry-flow-c"
    )

    for topic in "${topics[@]}"; do
        log_info "Verificando topic: $topic"
        if kubectl get kafkatopic -n "$KAFKA_NAMESPACE" "$topic" &>/dev/null; then
            log_success "Topic $topic existe"
        else
            log_error "Topic $topic NÃO encontrado"
        fi
    done

    # Verificar consumer groups (requer acesso ao Kafka)
    log_info "Verificando consumer groups..."
    local kafka_pod
    kafka_pod=$(kubectl get pods -n "$KAFKA_NAMESPACE" -l "strimzi.io/cluster=${KAFKA_CLUSTER},strimzi.io/name=${KAFKA_CLUSTER}-kafka" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$kafka_pod" ]; then
        local groups
        groups=$(kubectl exec -n "$KAFKA_NAMESPACE" "$kafka_pod" -- kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list 2>/dev/null || echo "")
        if echo "$groups" | grep -q "flow-c\|orchestrator\|worker"; then
            log_success "Consumer groups ativos detectados"
        else
            log_warn "Nenhum consumer group relacionado ao Flow C detectado"
        fi
    else
        log_warn "Pod Kafka não encontrado, pulando verificação de consumer groups"
    fi

    echo
}

# Verificar workers registrados
check_registered_workers() {
    log_info "=== Verificando Workers Registrados ==="

    local registry_service="service-registry"
    local worker_count=0

    if kubectl get svc -n "$SERVICE_REGISTRY_NAMESPACE" "$registry_service" >/dev/null 2>&1; then
        # Health check gRPC
        kubectl port-forward -n "$SERVICE_REGISTRY_NAMESPACE" "svc/${registry_service}" 50051:50051 >/tmp/validate-phase2-integration-sr-grpc.log 2>&1 &
        local sr_pf=$!
        sleep 2
        if command -v grpcurl >/dev/null 2>&1; then
            if grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check >/dev/null 2>&1; then
                log_success "Service Registry gRPC health responde"
            else
                log_warn "Service Registry gRPC health não respondeu"
            fi
        else
            log_warn "grpcurl não encontrado - pulando health gRPC"
        fi

        # Métricas Prometheus para contar workers
        kubectl port-forward -n "$SERVICE_REGISTRY_NAMESPACE" "svc/${registry_service}" 9090:9090 >/tmp/validate-phase2-integration-sr-metrics.log 2>&1 &
        local sr_metrics_pf=$!
        sleep 2
        worker_count=$(curl -s http://127.0.0.1:9090/metrics 2>/dev/null | awk -F' ' '/neural_hive_service_registry_agents_total.*agent_type="worker".*status="healthy"/{print $2}' | head -1)
        worker_count=${worker_count:-0}

        kill "$sr_pf" "$sr_metrics_pf" 2>/dev/null || true

        if [ "$worker_count" -gt 0 ]; then
            log_success "$worker_count workers registrados no Service Registry"
        else
            log_warn "Nenhum worker registrado no Service Registry"
        fi
    else
        log_error "Service Registry service não encontrado no namespace ${SERVICE_REGISTRY_NAMESPACE}"
    fi

    echo
}

# Verificar métricas Prometheus
check_prometheus_metrics() {
    log_info "=== Verificando Métricas Prometheus ==="

    local prometheus_pod
    prometheus_pod=$(kubectl get pods -n "$MONITORING_NAMESPACE" -l app=prometheus -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -z "$prometheus_pod" ]; then
        log_warn "Prometheus pod não encontrado, pulando verificação de métricas"
        echo
        return
    fi

    # Métricas Flow C esperadas
    local metrics=(
        "neural_hive_flow_c_duration_seconds"
        "neural_hive_flow_c_steps_duration_seconds"
        "neural_hive_flow_c_success_total"
        "neural_hive_worker_tasks_processed_total"
        "neural_hive_code_forge_pipelines_completed_total"
    )

    for metric in "${metrics[@]}"; do
        log_info "Verificando métrica: $metric"
        # Query Prometheus API
        local result
        result=$(kubectl exec -n "$MONITORING_NAMESPACE" "$prometheus_pod" -- wget -q -O- "http://localhost:9090/api/v1/query?query=$metric" 2>/dev/null || echo "")

        if echo "$result" | jq -e '.data.result | length > 0' &>/dev/null; then
            log_success "Métrica $metric presente"
        else
            log_warn "Métrica $metric não encontrada ou sem dados"
        fi
    done

    echo
}

# Verificar Jaeger spans
check_jaeger_spans() {
    log_info "=== Verificando Jaeger Spans ==="

    local jaeger_pod
    jaeger_pod=$(kubectl get pods -n "$MONITORING_NAMESPACE" -l app=jaeger -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -z "$jaeger_pod" ]; then
        log_warn "Jaeger pod não encontrado, pulando verificação de spans"
        echo
        return
    fi

    # Verificar se há traces (query Jaeger API)
    local traces
    traces=$(kubectl exec -n "$MONITORING_NAMESPACE" "$jaeger_pod" -- wget -q -O- "http://localhost:16686/api/traces?service=flow_c_orchestrator&limit=10" 2>/dev/null || echo "")

    if echo "$traces" | jq -e '.data | length > 0' &>/dev/null; then
        log_success "Traces detectados no Jaeger para flow_c_orchestrator"
    else
        log_warn "Nenhum trace encontrado no Jaeger para flow_c_orchestrator"
    fi

    echo
}

# Verificar Grafana dashboard
check_grafana_dashboard() {
    log_info "=== Verificando Grafana Dashboard ==="

    # Verificar se ConfigMap do dashboard existe
    if kubectl get configmap -n "$MONITORING_NAMESPACE" grafana-dashboard-flow-c &>/dev/null; then
        log_success "ConfigMap grafana-dashboard-flow-c existe"
    else
        log_warn "ConfigMap grafana-dashboard-flow-c NÃO encontrado"
    fi

    # Verificar Grafana pod
    local grafana_pod
    grafana_pod=$(kubectl get pods -n "$MONITORING_NAMESPACE" -l app=grafana -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -n "$grafana_pod" ]; then
        log_success "Grafana pod rodando: $grafana_pod"
    else
        log_warn "Grafana pod não encontrado"
    fi

    echo
}

# Verificar Prometheus alert rules
check_prometheus_alerts() {
    log_info "=== Verificando Prometheus Alert Rules ==="

    local prometheus_pod
    prometheus_pod=$(kubectl get pods -n "$MONITORING_NAMESPACE" -l app=prometheus -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -z "$prometheus_pod" ]; then
        log_warn "Prometheus pod não encontrado, pulando verificação de alertas"
        echo
        return
    fi

    # Verificar rules carregadas
    local rules
    rules=$(kubectl exec -n "$MONITORING_NAMESPACE" "$prometheus_pod" -- wget -q -O- "http://localhost:9090/api/v1/rules" 2>/dev/null || echo "")

    if echo "$rules" | jq -e '.data.groups[] | select(.name=="flow-c-integration")' &>/dev/null; then
        log_success "Alert rules 'flow-c-integration' carregadas no Prometheus"
    else
        log_warn "Alert rules 'flow-c-integration' NÃO encontradas no Prometheus"
    fi

    echo
}

# Print summary
print_summary() {
    echo
    echo "========================================"
    log_info "=== SUMMARY ==="
    echo "========================================"
    echo -e "${GREEN}Checks Passed:${NC}  $CHECKS_PASSED"
    echo -e "${YELLOW}Checks Warned:${NC}  $CHECKS_WARNED"
    echo -e "${RED}Checks Failed:${NC}  $CHECKS_FAILED"
    echo "========================================"

    if [ "$CHECKS_FAILED" -eq 0 ]; then
        log_success "=== VALIDAÇÃO PASSOU ==="
        return 0
    else
        log_error "=== VALIDAÇÃO FALHOU ==="
        return 1
    fi
}

# Main
main() {
    parse_args "$@"
    ORCH_NAMESPACE="${ORCH_NAMESPACE:-$NAMESPACE}"

    log_info "=== Validate Phase 2 Flow C Integration ==="
    log_info "Namespaces: orch=$ORCH_NAMESPACE | registry=$SERVICE_REGISTRY_NAMESPACE | workers=$WORKERS_NAMESPACE | monitoring=$MONITORING_NAMESPACE | kafka=$KAFKA_NAMESPACE"
    echo

    check_pods_and_rollouts
    check_service_connectivity
    check_kafka_topics
    check_registered_workers
    check_prometheus_metrics
    check_jaeger_spans
    check_grafana_dashboard
    check_prometheus_alerts

    print_summary
}

main "$@"
