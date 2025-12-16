#!/bin/bash
# Teste E2E de integração Phase 2 Flow C
# Valida o fluxo completo: Intent → Decision → Orchestration → Tickets → Workers → Code Forge → Deploy

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Namespaces (podem ser sobrescritos via env)
ORCH_NAMESPACE="${ORCH_NAMESPACE:-neural-hive-orchestration}"
ORCHESTRATOR_SERVICE="${ORCHESTRATOR_SERVICE:-orchestrator-dynamic}"
SERVICE_REGISTRY_NAMESPACE="${SERVICE_REGISTRY_NAMESPACE:-neural-hive-service-registry}"
WORKERS_NAMESPACE="${WORKERS_NAMESPACE:-neural-hive-workers}"
KAFKA_NAMESPACE="${KAFKA_NAMESPACE:-neural-hive-kafka}"
KAFKA_CLUSTER="${KAFKA_CLUSTER:-neural-hive-kafka}"
MESSAGING_NAMESPACE="${MESSAGING_NAMESPACE:-neural-hive-kafka}"
MONITORING_NAMESPACE="${MONITORING_NAMESPACE:-neural-hive-observability}"
PROMETHEUS_SERVICE="${PROMETHEUS_SERVICE:-prometheus}"
CODE_FORGE_NAMESPACE="${CODE_FORGE_NAMESPACE:-neural-hive-code-forge}"
SERVICE_REGISTRY_SERVICE="${SERVICE_REGISTRY_SERVICE:-service-registry}"

# Contadores de checks
CHECKS_PASSED=0
CHECKS_TOTAL=0
SR_GRPC_PF_PID=""
SR_METRICS_PF_PID=""

record_check() {
    local description="$1"
    local status="$2" # pass|fail|warn
    ((CHECKS_TOTAL++))
    if [ "$status" = "pass" ]; then
        ((CHECKS_PASSED++))
    fi
}

echo "========================================"
echo "  Phase 2 Flow C Integration Test E2E"
echo "========================================"
echo ""

# Função para log
log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

PROM_PF_PID=""
cleanup() {
    if [ -n "$PROM_PF_PID" ]; then
        kill "$PROM_PF_PID" 2>/dev/null || true
    fi
    if [ -n "$SR_GRPC_PF_PID" ]; then
        kill "$SR_GRPC_PF_PID" 2>/dev/null || true
    fi
    if [ -n "$SR_METRICS_PF_PID" ]; then
        kill "$SR_METRICS_PF_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

start_prometheus_port_forward() {
    if [ -n "$PROM_PF_PID" ] && kill -0 "$PROM_PF_PID" 2>/dev/null; then
        return
    fi

    if kubectl get svc -n "$MONITORING_NAMESPACE" "$PROMETHEUS_SERVICE" >/dev/null 2>&1; then
        kubectl port-forward -n "$MONITORING_NAMESPACE" "svc/${PROMETHEUS_SERVICE}" 9090:9090 >/tmp/phase2-flow-c-prometheus.log 2>&1 &
        PROM_PF_PID=$!
        sleep 2
    else
        warn "Prometheus service ${PROMETHEUS_SERVICE} não encontrado no namespace ${MONITORING_NAMESPACE}"
    fi
}

prom_query() {
    local expr="$1"
    start_prometheus_port_forward
    local encoded
    encoded=$(python3 - <<'PY' "${expr}")
import sys, urllib.parse
print(urllib.parse.quote(sys.argv[1], safe=""))
PY
    curl -s "http://127.0.0.1:9090/api/v1/query?query=${encoded}" 2>/dev/null
}

# 1. Verificar dependências
log "Verificando dependências..."
command -v kubectl >/dev/null 2>&1 || { error "kubectl não encontrado"; exit 1; }
command -v curl >/dev/null 2>&1 || { error "curl não encontrado"; exit 1; }
command -v jq >/dev/null 2>&1 || { error "jq não encontrado"; exit 1; }
command -v bc >/dev/null 2>&1 || { error "bc não encontrado"; exit 1; }
command -v python3 >/dev/null 2>&1 || { error "python3 não encontrado"; exit 1; }

# 2. Verificar serviços rodando
log "Verificando serviços Kubernetes..."

SERVICES=(
    "orchestrator-dynamic:${ORCH_NAMESPACE}"
    "service-registry:${SERVICE_REGISTRY_NAMESPACE}"
    "execution-ticket-service:${ORCH_NAMESPACE}"
    "worker-agents:${WORKERS_NAMESPACE}"
    "code-forge:${CODE_FORGE_NAMESPACE}"
)

for service_ns in "${SERVICES[@]}"; do
    IFS=':' read -r service namespace <<<"$service_ns"
    if kubectl get svc "$service" -n "$namespace" >/dev/null 2>&1; then
        log "✓ Serviço $service encontrado em $namespace"
        record_check "svc-${service}" "pass"
    else
        warn "✗ Serviço $service não encontrado em $namespace"
        record_check "svc-${service}" "fail"
    fi
done

# 3. Verificar tópicos Kafka
log "Verificando tópicos Kafka..."
if kubectl get kafkatopic telemetry-flow-c -n "$MESSAGING_NAMESPACE" >/dev/null 2>&1; then
    log "✓ Tópico telemetry-flow-c existe em $MESSAGING_NAMESPACE"
    record_check "kafka-topic-telemetry-flow-c" "pass"
else
    warn "✗ Tópico telemetry-flow-c não encontrado em $MESSAGING_NAMESPACE"
    record_check "kafka-topic-telemetry-flow-c" "fail"
fi

# 4. Teste de descoberta de workers
log "Testando descoberta de workers via Service Registry..."

WORKER_COUNT=0
SR_HEALTH_STATUS="skip"

if kubectl get svc -n "$SERVICE_REGISTRY_NAMESPACE" "$SERVICE_REGISTRY_SERVICE" >/dev/null 2>&1; then
    # gRPC health check
    kubectl port-forward -n "$SERVICE_REGISTRY_NAMESPACE" "svc/${SERVICE_REGISTRY_SERVICE}" 50051:50051 >/tmp/phase2-flow-c-sr-grpc.log 2>&1 &
    SR_GRPC_PF_PID=$!
    sleep 2
    if command -v grpcurl >/dev/null 2>&1; then
        if grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check >/dev/null 2>&1; then
            log "✓ Service Registry (gRPC) responde health check"
            SR_HEALTH_STATUS="pass"
        else
            warn "✗ Service Registry gRPC health check falhou"
            SR_HEALTH_STATUS="fail"
        fi
    else
        warn "grpcurl não disponível para validar gRPC health"
    fi

    # Métricas Prometheus para contar workers (porta dedicada para evitar conflito com Prometheus principal)
    kubectl port-forward -n "$SERVICE_REGISTRY_NAMESPACE" "svc/${SERVICE_REGISTRY_SERVICE}" 9091:9090 >/tmp/phase2-flow-c-sr-metrics.log 2>&1 &
    SR_METRICS_PF_PID=$!
    sleep 2
    WORKER_COUNT=$(curl -s http://127.0.0.1:9091/metrics 2>/dev/null | awk -F' ' '/neural_hive_service_registry_agents_total.*agent_type="worker".*status="healthy"/{print $2}' | head -1)
    WORKER_COUNT=${WORKER_COUNT:-0}
    kill "$SR_METRICS_PF_PID" 2>/dev/null || true
    SR_METRICS_PF_PID=""
else
    warn "✗ Service Registry service não encontrado em ${SERVICE_REGISTRY_NAMESPACE}"
fi

if [ "${WORKER_COUNT:-0}" -gt 0 ]; then
    log "✓ Workers disponíveis: $WORKER_COUNT"
    record_check "workers-available" "pass"
else
    warn "✗ Nenhum worker disponível"
    record_check "workers-available" "fail"
fi
if [ "$SR_HEALTH_STATUS" != "skip" ]; then
    record_check "service-registry-health" "$SR_HEALTH_STATUS"
fi

# 5. Teste de endpoint Flow C status
log "Testando endpoint /api/v1/flow-c/status..."

ORCH_HOST="${ORCHESTRATOR_SERVICE}.${ORCH_NAMESPACE}.svc.cluster.local"
STATUS_RESPONSE=$(curl -s "http://${ORCH_HOST}:8000/api/v1/flow-c/status" 2>/dev/null || echo "{}")
TOTAL_PROCESSED=$(echo "$STATUS_RESPONSE" | jq -r '.total_processed // 0')
SUCCESS_RATE=$(echo "$STATUS_RESPONSE" | jq -r '.success_rate // 0')

log "Total processado: $TOTAL_PROCESSED"
log "Taxa de sucesso: $SUCCESS_RATE%"
if [ "$TOTAL_PROCESSED" != "null" ] && [ -n "$STATUS_RESPONSE" ]; then
    record_check "flow-c-status-endpoint" "pass"
else
    record_check "flow-c-status-endpoint" "fail"
fi

# 6. Teste de métricas Prometheus
log "Verificando métricas Prometheus Flow C..."

METRICS=(
    "neural_hive_flow_c_duration_seconds"
    "neural_hive_flow_c_success_total"
    "neural_hive_flow_c_steps_duration_seconds"
    "neural_hive_flow_c_telemetry_buffer_size"
)

for metric in "${METRICS[@]}"; do
    METRIC_EXISTS=$(prom_query "$metric" | jq -r '.data.result | length' 2>/dev/null || echo "0")
    if [ "$METRIC_EXISTS" != "0" ]; then
        log "✓ Métrica $metric disponível"
        record_check "metric-${metric}" "pass"
    else
        warn "✗ Métrica $metric não encontrada"
        record_check "metric-${metric}" "fail"
    fi
done

# 7. Teste simulado de execução Flow C
log "Simulando execução Flow C..."

DECISION_PAYLOAD=$(cat <<EOF
{
  "intent_id": "test-intent-$(date +%s)",
  "plan_id": "test-plan-$(date +%s)",
  "decision_id": "test-decision-$(date +%s)",
  "correlation_id": "test-corr-$(date +%s)",
  "priority": 5,
  "risk_band": "low",
  "cognitive_plan": {
    "tasks": [
      {
        "type": "code_generation",
        "template_id": "test_template",
        "parameters": {"test": true},
        "capabilities": ["python"],
        "description": "Test task"
      }
    ]
  }
}
EOF
)

# Enviar decisão para Flow C (se endpoint disponível)
if curl -s "http://${ORCH_HOST}:8000/health" >/dev/null 2>&1; then
    FLOW_RESPONSE=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "$DECISION_PAYLOAD" \
        "http://${ORCH_HOST}:8000/api/v1/flow-c/execute" 2>/dev/null || echo "{}")

    if [ -n "$FLOW_RESPONSE" ] && [ "$FLOW_RESPONSE" != "{}" ]; then
        log "✓ Flow C executado com sucesso"
        record_check "flow-c-execution" "pass"
    else
        warn "✗ Falha ao executar Flow C (endpoint pode não estar implementado)"
        record_check "flow-c-execution" "fail"
    fi
else
    warn "✗ Orchestrator não acessível"
    record_check "flow-c-execution" "fail"
fi

# 8. Verificar alertas Prometheus
log "Verificando alertas Prometheus Flow C..."

if [ -f "$PROJECT_ROOT/monitoring/alerts/flow-c-integration-alerts.yaml" ]; then
    ALERT_COUNT=$(grep -c "alert:" "$PROJECT_ROOT/monitoring/alerts/flow-c-integration-alerts.yaml" || echo "0")
    log "✓ Alertas Flow C configurados: $ALERT_COUNT"
    record_check "alerts-file" "pass"
else
    warn "✗ Arquivo de alertas não encontrado"
    record_check "alerts-file" "fail"
fi

# 9. Verificar dashboard Grafana
log "Verificando dashboard Grafana..."

if [ -f "$PROJECT_ROOT/monitoring/dashboards/fluxo-c-orquestracao.json" ]; then
    PANEL_COUNT=$(grep -c '"title"' "$PROJECT_ROOT/monitoring/dashboards/fluxo-c-orquestracao.json" || echo "0")
    log "✓ Dashboard Flow C configurado com $PANEL_COUNT painéis"
    record_check "grafana-dashboard" "pass"
else
    warn "✗ Dashboard não encontrado"
    record_check "grafana-dashboard" "fail"
fi

# 10. Validação SLO
log "Validando SLOs..."

LATENCY_EXPR='histogram_quantile(0.95,rate(neural_hive_flow_c_duration_seconds_bucket[5m]))'
SUCCESS_EXPR='(rate(neural_hive_flow_c_success_total[10m])/(rate(neural_hive_flow_c_success_total[10m])+rate(neural_hive_flow_c_failures_total[10m])))'
SLA_EXPR='rate(neural_hive_flow_c_sla_violations_total[30m])'

LATENCY_VALUE=$(prom_query "$LATENCY_EXPR" | jq -r '.data.result[0].value[1]' 2>/dev/null || echo "")
SUCCESS_VALUE=$(prom_query "$SUCCESS_EXPR" | jq -r '.data.result[0].value[1]' 2>/dev/null || echo "")
SLA_VALUE=$(prom_query "$SLA_EXPR" | jq -r '.data.result[0].value[1]' 2>/dev/null || echo "")

if [ -n "$LATENCY_VALUE" ] && [ "$LATENCY_VALUE" != "null" ]; then
    LATENCY_SECONDS=$(printf "%.0f" "$(echo "$LATENCY_VALUE" | bc -l)")
    if (( LATENCY_SECONDS < 14400 )); then
        log "✓ Latência p95 (5m) ${LATENCY_SECONDS}s < 4h"
        record_check "slo-latency" "pass"
    else
        warn "✗ Latência p95 (5m) ${LATENCY_SECONDS}s >= 4h"
        record_check "slo-latency" "fail"
    fi
else
    warn "✗ Latência p95 não disponível"
    record_check "slo-latency" "fail"
fi

if [ -n "$SUCCESS_VALUE" ] && [ "$SUCCESS_VALUE" != "null" ]; then
    SUCCESS_PERCENT=$(echo "$SUCCESS_VALUE * 100" | bc -l | xargs printf "%.2f")
    if (( $(echo "$SUCCESS_PERCENT >= 99" | bc -l) )); then
        log "✓ Taxa de sucesso (10m) ${SUCCESS_PERCENT}% >= 99%"
        record_check "slo-success-rate" "pass"
    else
        warn "✗ Taxa de sucesso (10m) ${SUCCESS_PERCENT}% < 99%"
        record_check "slo-success-rate" "fail"
    fi
else
    warn "✗ Taxa de sucesso não disponível"
    record_check "slo-success-rate" "fail"
fi

if [ -n "$SLA_VALUE" ] && [ "$SLA_VALUE" != "null" ]; then
    SLA_RATE=$(printf "%.4f" "$SLA_VALUE")
    if (( $(echo "$SLA_RATE == 0" | bc -l) )); then
        log "✓ Nenhuma violação de SLA nos últimos 30m"
        record_check "slo-sla-violations" "pass"
    else
        warn "✗ Violações de SLA detectadas (taxa ${SLA_RATE}/s nos últimos 30m)"
        record_check "slo-sla-violations" "fail"
    fi
else
    warn "✗ Métrica de violações de SLA indisponível"
    record_check "slo-sla-violations" "fail"
fi

# 11. Resumo
echo ""
echo "========================================"
echo "  Resumo do Teste E2E"
echo "========================================"
echo ""

if [ "$CHECKS_TOTAL" -eq 0 ]; then
    PASS_RATE=0
else
    PASS_RATE=$((CHECKS_PASSED * 100 / CHECKS_TOTAL))
fi

echo "Checks passados: $CHECKS_PASSED/$CHECKS_TOTAL ($PASS_RATE%)"
echo ""

if [ $PASS_RATE -ge 80 ]; then
    log "✓ Integração Flow C validada com sucesso!"
    exit 0
else
    error "✗ Integração Flow C apresenta problemas"
    exit 1
fi
