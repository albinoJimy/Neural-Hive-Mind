#!/bin/bash
# Validação completa OTEL Collector + Jaeger para Neural Hive

set -euo pipefail

NAMESPACE="${NAMESPACE:-observability}"
REPORT_FILE="${REPORT_FILE:-otel-jaeger-validation-report.json}"
NET_DEBUG_IMAGE="${NET_DEBUG_IMAGE:-busybox:1.36}"

# Cores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; ((PASSED++)); }
error() { echo -e "${RED}[✗]${NC} $1"; ((FAILED++)); }
warning() { echo -e "${YELLOW}[!]${NC} $1"; ((WARNINGS++)); }

PASSED=0
FAILED=0
WARNINGS=0
TOTAL=0
FAILED_INFRA=0
FAILED_OTEL=0
FAILED_JAEGER=0
FAILED_CONNECTIVITY=0
FAILED_SAMPLING=0
FAILED_E2E=0

run_section_test() {
  local section="$1"
  local name="$2"
  local cmd="$3"
  ((TOTAL++))
  log "Teste $TOTAL: $name"
  if eval "$cmd" &>/dev/null; then
    success "$name"
    return 0
  else
    error "$name"
    case "$section" in
      infra) ((FAILED_INFRA++)) ;;
      otel) ((FAILED_OTEL++)) ;;
      jaeger) ((FAILED_JAEGER++)) ;;
      connectivity) ((FAILED_CONNECTIVITY++)) ;;
      sampling) ((FAILED_SAMPLING++)) ;;
      e2e) ((FAILED_E2E++)) ;;
    esac
    return 1
  fi
}

run_in_netpod() {
  local description="$1"
  local cmd="$2"
  local pod="netcheck-$RANDOM"
  if ! kubectl run "$pod" -n "$NAMESPACE" --rm --restart=Never --image="$NET_DEBUG_IMAGE" --command -- sh -c "$cmd" >/dev/null 2>&1; then
    error "$description (falha ao executar no pod utilitário $NET_DEBUG_IMAGE)"
    return 1
  fi
  return 0
}

log "=== Validação Completa OTEL Collector + Jaeger ==="
log "Namespace: $NAMESPACE"
echo ""

# Seção 1: Infraestrutura
log "[Seção 1/6] Validando Infraestrutura..."
run_section_test infra "OTEL Collector deployment existe" "kubectl get deployment -n $NAMESPACE neural-hive-otel-collector"
run_section_test infra "OTEL Collector pods Running" "kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=neural-hive-otel-collector -o jsonpath='{.items[0].status.phase}' | grep -q Running"
run_section_test infra "Jaeger Collector deployment existe" "kubectl get deployment -n $NAMESPACE jaeger-collector"
run_section_test infra "Jaeger Collector pods Running" "kubectl get pods -n $NAMESPACE -l app.kubernetes.io/component=collector -o jsonpath='{.items[0].status.phase}' | grep -q Running"
run_section_test infra "Jaeger Query deployment existe" "kubectl get deployment -n $NAMESPACE jaeger-query"
run_section_test infra "Jaeger Query pods Running" "kubectl get pods -n $NAMESPACE -l app.kubernetes.io/component=query -o jsonpath='{.items[0].status.phase}' | grep -q Running"

# Seção 2: Configuração OTEL Collector
log "[Seção 2/6] Validando Configuração OTEL Collector..."
run_section_test otel "OTEL health endpoint responde" "run_in_netpod \"OTEL health endpoint\" \"wget -qO- http://neural-hive-otel-collector:13133/\""
run_section_test otel "OTEL receivers configurados" "run_in_netpod \"OTEL receivers\" \"wget -qO- http://neural-hive-otel-collector:8888/metrics | grep -q otelcol_receiver_accepted_spans\""
run_section_test otel "OTEL processors configurados" "run_in_netpod \"OTEL processors\" \"wget -qO- http://neural-hive-otel-collector:8888/metrics | grep -q otelcol_processor_batch\""
run_section_test otel "OTEL exporters configurados" "run_in_netpod \"OTEL exporters\" \"wget -qO- http://neural-hive-otel-collector:8888/metrics | grep -q 'otelcol_exporter_sent_spans{exporter=\\\"jaeger\\\"}'\""
run_section_test otel "Teste pipeline OTEL (script dedicado)" "NAMESPACE=$NAMESPACE ./scripts/observability/test-otel-pipeline.sh"

# Seção 3: Configuração Jaeger
log "[Seção 3/6] Validando Configuração Jaeger..."
JAEGER_POD=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/component=collector -o jsonpath='{.items[0].metadata.name}')
run_section_test jaeger "Jaeger Collector health endpoint responde" "run_in_netpod \"Jaeger health\" \"wget -qO- http://jaeger-collector:14269/\""
run_section_test jaeger "Jaeger OTLP receiver habilitado" "kubectl logs -n $NAMESPACE $JAEGER_POD --tail=100 | grep -q 'OTLP.*enabled'"
run_section_test jaeger "Jaeger conectado ao Elasticsearch" "run_in_netpod \"Jaeger -> Elasticsearch\" \"wget -qO- http://elasticsearch:9200/_cluster/health | grep -q 'status'\""

# Seção 4: Conectividade
log "[Seção 4/6] Validando Conectividade..."
run_section_test connectivity "DNS resolve jaeger-collector" "run_in_netpod \"DNS jaeger-collector\" \"nslookup jaeger-collector.$NAMESPACE.svc.cluster.local\""
run_section_test connectivity "Porta 14250 (Jaeger gRPC) acessível" "run_in_netpod \"Porta 14250\" \"nc -z -w5 jaeger-collector.$NAMESPACE.svc.cluster.local 14250\""
run_section_test connectivity "Porta 4317 (OTLP gRPC) acessível" "run_in_netpod \"Porta 4317\" \"nc -z -w5 jaeger-collector.$NAMESPACE.svc.cluster.local 4317\""

# Seção 5: Sampling Strategies
log "[Seção 5/6] Validando Sampling Strategies..."
run_section_test sampling "Sampling strategies ConfigMap existe" "kubectl get configmap -n $NAMESPACE jaeger-sampling-strategies"
run_section_test sampling "Sampling strategies montado no collector" "kubectl describe deployment -n $NAMESPACE jaeger-collector | grep -q 'sampling-strategies'"

# Seção 6: Teste E2E
log "[Seção 6/6] Executando Teste E2E..."
TRACE_ID=$(openssl rand -hex 16)
INTENT_ID="validation-$(uuidgen)"

kubectl port-forward -n $NAMESPACE svc/neural-hive-otel-collector 4318:4318 > /dev/null 2>&1 &
PF_PID=$!
sleep 3

curl -s -X POST http://localhost:4318/v1/traces \
  -H "Content-Type: application/json" \
  -H "x-neural-hive-intent-id: $INTENT_ID" \
  -d '{
    "resourceSpans": [{
      "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "validation-test"}}]},
      "scopeSpans": [{
        "spans": [{
          "traceId": "'$TRACE_ID'",
          "spanId": "'$(openssl rand -hex 8)'",
          "name": "validation-operation",
          "kind": 1,
          "startTimeUnixNano": "'$(($(date +%s%N)))'",
          "endTimeUnixNano": "'$(($(date +%s%N) + 1000000000))'",
          "attributes": [{"key": "neural.hive.intent.id", "value": {"stringValue": "'$INTENT_ID'"}}]
        }]
      }]
    }]
  }' > /dev/null

kill $PF_PID 2>/dev/null
sleep 35

kubectl port-forward -n $NAMESPACE svc/jaeger-query 16686:16686 > /dev/null 2>&1 &
PF_PID=$!
sleep 3

TRACE_FOUND=$(curl -s "http://localhost:16686/api/traces?service=validation-test&tag=neural.hive.intent.id:$INTENT_ID" | jq -r '.data[0].traceID // "not_found"')
kill $PF_PID 2>/dev/null

((TOTAL++))
if [ "$TRACE_FOUND" != "not_found" ]; then
  success "Trace E2E encontrado no Jaeger"
else
  error "Trace E2E não encontrado no Jaeger"
  ((FAILED_E2E++))
fi

# Gerar relatório JSON
cat > "$REPORT_FILE" << EOF
{
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "namespace": "$NAMESPACE",
  "summary": {
    "total_tests": $TOTAL,
    "passed": $PASSED,
    "failed": $FAILED,
    "warnings": $WARNINGS,
    "success_rate": $(awk "BEGIN {printf \"%.1f\", $PASSED/$TOTAL*100}")
  },
  "sections": {
    "infrastructure": "$([ $FAILED_INFRA -eq 0 ] && echo "pass" || echo "fail")",
    "otel_config": "$([ $FAILED_OTEL -eq 0 ] && echo "pass" || echo "fail")",
    "jaeger_config": "$([ $FAILED_JAEGER -eq 0 ] && echo "pass" || echo "fail")",
    "connectivity": "$([ $FAILED_CONNECTIVITY -eq 0 ] && echo "pass" || echo "fail")",
    "sampling": "$([ $FAILED_SAMPLING -eq 0 ] && echo "pass" || echo "fail")",
    "e2e_test": "$([ $FAILED_E2E -eq 0 ] && echo "pass" || echo "fail")"
  }
}
EOF

# Resumo
echo ""
log "=== Resumo da Validação ==="
log "Total de testes: $TOTAL"
echo -e "${GREEN}[✓]${NC} Testes aprovados: $PASSED"
[ $FAILED -gt 0 ] && echo -e "${RED}[✗]${NC} Testes falharam: $FAILED"
[ $WARNINGS -gt 0 ] && warning "Avisos: $WARNINGS"
log "Taxa de sucesso: $(awk "BEGIN {printf \"%.1f\", $PASSED/$TOTAL*100}")%"
log "Relatório salvo em: $REPORT_FILE"

[ $FAILED -eq 0 ] && exit 0 || exit 1
