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

# 1. Verificar dependências
log "Verificando dependências..."
command -v kubectl >/dev/null 2>&1 || { error "kubectl não encontrado"; exit 1; }
command -v curl >/dev/null 2>&1 || { error "curl não encontrado"; exit 1; }
command -v jq >/dev/null 2>&1 || { error "jq não encontrado"; exit 1; }

# 2. Verificar serviços rodando
log "Verificando serviços Kubernetes..."

SERVICES=(
    "orchestrator-dynamic"
    "service-registry"
    "execution-ticket-service"
    "worker-agents"
    "code-forge"
)

for service in "${SERVICES[@]}"; do
    if kubectl get svc "$service" -n neural-hive-orchestration >/dev/null 2>&1; then
        log "✓ Serviço $service encontrado"
    else
        warn "✗ Serviço $service não encontrado"
    fi
done

# 3. Verificar tópicos Kafka
log "Verificando tópicos Kafka..."
kubectl get kafkatopic telemetry-flow-c -n neural-hive-messaging >/dev/null 2>&1 && \
    log "✓ Tópico telemetry-flow-c existe" || \
    warn "✗ Tópico telemetry-flow-c não encontrado"

# 4. Teste de descoberta de workers
log "Testando descoberta de workers via Service Registry..."

WORKER_COUNT=$(curl -s http://service-registry.neural-hive-orchestration:50051/agents?type=worker 2>/dev/null | jq -r '.agents | length' || echo "0")
if [ "$WORKER_COUNT" -gt 0 ]; then
    log "✓ Workers disponíveis: $WORKER_COUNT"
else
    warn "✗ Nenhum worker disponível"
fi

# 5. Teste de endpoint Flow C status
log "Testando endpoint /api/v1/flow-c/status..."

STATUS_RESPONSE=$(curl -s http://orchestrator-dynamic.neural-hive-orchestration:8000/api/v1/flow-c/status 2>/dev/null || echo "{}")
TOTAL_PROCESSED=$(echo "$STATUS_RESPONSE" | jq -r '.total_processed // 0')
SUCCESS_RATE=$(echo "$STATUS_RESPONSE" | jq -r '.success_rate // 0')

log "Total processado: $TOTAL_PROCESSED"
log "Taxa de sucesso: $SUCCESS_RATE%"

# 6. Teste de métricas Prometheus
log "Verificando métricas Prometheus Flow C..."

METRICS=(
    "neural_hive_flow_c_duration_seconds"
    "neural_hive_flow_c_success_total"
    "neural_hive_flow_c_steps_duration_seconds"
    "neural_hive_flow_c_telemetry_buffer_size"
)

PROMETHEUS_URL="http://prometheus.neural-hive-monitoring:9090"

for metric in "${METRICS[@]}"; do
    METRIC_EXISTS=$(curl -s "${PROMETHEUS_URL}/api/v1/query?query=${metric}" 2>/dev/null | jq -r '.data.result | length')
    if [ "$METRIC_EXISTS" != "0" ]; then
        log "✓ Métrica $metric disponível"
    else
        warn "✗ Métrica $metric não encontrada"
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
if curl -s http://orchestrator-dynamic.neural-hive-orchestration:8000/health >/dev/null 2>&1; then
    FLOW_RESPONSE=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "$DECISION_PAYLOAD" \
        http://orchestrator-dynamic.neural-hive-orchestration:8000/api/v1/flow-c/execute 2>/dev/null || echo "{}")

    if [ -n "$FLOW_RESPONSE" ] && [ "$FLOW_RESPONSE" != "{}" ]; then
        log "✓ Flow C executado com sucesso"
    else
        warn "✗ Falha ao executar Flow C (endpoint pode não estar implementado)"
    fi
else
    warn "✗ Orchestrator não acessível"
fi

# 8. Verificar alertas Prometheus
log "Verificando alertas Prometheus Flow C..."

if [ -f "$PROJECT_ROOT/monitoring/alerts/flow-c-integration-alerts.yaml" ]; then
    ALERT_COUNT=$(grep -c "alert:" "$PROJECT_ROOT/monitoring/alerts/flow-c-integration-alerts.yaml" || echo "0")
    log "✓ Alertas Flow C configurados: $ALERT_COUNT"
else
    warn "✗ Arquivo de alertas não encontrado"
fi

# 9. Verificar dashboard Grafana
log "Verificando dashboard Grafana..."

if [ -f "$PROJECT_ROOT/monitoring/dashboards/fluxo-c-orquestracao.json" ]; then
    PANEL_COUNT=$(grep -c '"title"' "$PROJECT_ROOT/monitoring/dashboards/fluxo-c-orquestracao.json" || echo "0")
    log "✓ Dashboard Flow C configurado com $PANEL_COUNT painéis"
else
    warn "✗ Dashboard não encontrado"
fi

# 10. Validação SLO
log "Validando SLOs..."

echo ""
echo "SLOs definidos:"
echo "  - Latência Intent→Deploy: < 4h (p95)"
echo "  - Taxa de sucesso: > 99%"
echo ""

if [ "$SUCCESS_RATE" != "0" ]; then
    if (( $(echo "$SUCCESS_RATE >= 99" | bc -l) )); then
        log "✓ SLO Taxa de Sucesso: PASS ($SUCCESS_RATE% >= 99%)"
    else
        warn "✗ SLO Taxa de Sucesso: FAIL ($SUCCESS_RATE% < 99%)"
    fi
else
    warn "✗ SLO Taxa de Sucesso: Sem dados suficientes"
fi

# 11. Resumo
echo ""
echo "========================================"
echo "  Resumo do Teste E2E"
echo "========================================"
echo ""

CHECKS_PASSED=0
CHECKS_TOTAL=10

# Contar checks passados (simplificado)
[ "$WORKER_COUNT" -gt 0 ] && ((CHECKS_PASSED++))
[ "$TOTAL_PROCESSED" != "null" ] && ((CHECKS_PASSED++))
[ -f "$PROJECT_ROOT/monitoring/alerts/flow-c-integration-alerts.yaml" ] && ((CHECKS_PASSED++))
[ -f "$PROJECT_ROOT/monitoring/dashboards/fluxo-c-orquestracao.json" ] && ((CHECKS_PASSED++))

PASS_RATE=$((CHECKS_PASSED * 100 / CHECKS_TOTAL))

echo "Checks passados: $CHECKS_PASSED/$CHECKS_TOTAL ($PASS_RATE%)"
echo ""

if [ $PASS_RATE -ge 80 ]; then
    log "✓ Integração Flow C validada com sucesso!"
    exit 0
else
    error "✗ Integração Flow C apresenta problemas"
    exit 1
fi
