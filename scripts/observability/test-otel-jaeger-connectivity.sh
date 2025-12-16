#!/bin/bash
# Testar conectividade OTEL Collector → Jaeger Collector

set -euo pipefail

NAMESPACE="${NAMESPACE:-observability}"
NET_DEBUG_IMAGE="${NET_DEBUG_IMAGE:-busybox:1.36}"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "[$(date +'%H:%M:%S')] $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; }
warning() { echo -e "${YELLOW}[!]${NC} $1"; }

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

log "=== Teste de Conectividade OTEL Collector → Jaeger Collector ==="

# 1. Verificar resolução DNS
log "[1/6] Testando resolução DNS..."
if run_in_netpod "DNS jaeger-collector" "nslookup jaeger-collector.$NAMESPACE.svc.cluster.local | grep -q 'Address'"; then
  success "DNS resolve jaeger-collector.$NAMESPACE.svc.cluster.local"
else
  error "DNS não resolve jaeger-collector.$NAMESPACE.svc.cluster.local"
  exit 1
fi

# 2. Testar conectividade TCP Jaeger native (14250)
log "[2/6] Testando conectividade TCP Jaeger native :14250..."
if run_in_netpod "Porta 14250" "nc -z -w5 jaeger-collector.$NAMESPACE.svc.cluster.local 14250"; then
  success "Porta 14250 (Jaeger gRPC) acessível"
else
  error "Porta 14250 (Jaeger gRPC) não acessível"
  exit 1
fi

# 3. Testar conectividade TCP OTLP (4317)
log "[3/6] Testando conectividade TCP OTLP :4317..."
if run_in_netpod "Porta 4317" "nc -z -w5 jaeger-collector.$NAMESPACE.svc.cluster.local 4317"; then
  success "Porta 4317 (OTLP gRPC) acessível"
else
  error "Porta 4317 (OTLP gRPC) não acessível"
  exit 1
fi

# 4. Verificar métricas de export do OTEL Collector
log "[4/6] Verificando métricas de export..."
kubectl port-forward -n $NAMESPACE svc/neural-hive-otel-collector 8888:8888 > /dev/null 2>&1 &
PF_METRICS_PID=$!
sleep 3

JAEGER_SENT=$(curl -s http://localhost:8888/metrics | grep 'otelcol_exporter_sent_spans{exporter="jaeger"}' | awk '{print $2}' || echo "0")
OTLP_SENT=$(curl -s http://localhost:8888/metrics | grep 'otelcol_exporter_sent_spans{exporter="otlp/traces"}' | awk '{print $2}' || echo "0")

kill $PF_METRICS_PID 2>/dev/null

if [ "$JAEGER_SENT" != "0" ] || [ "$OTLP_SENT" != "0" ]; then
  success "OTEL Collector exportou spans (Jaeger: $JAEGER_SENT, OTLP: $OTLP_SENT)"
else
  warning "OTEL Collector ainda não exportou spans (pode ser normal se sem tráfego)"
fi

# 5. Verificar métricas de recebimento do Jaeger Collector
log "[5/6] Verificando métricas de recebimento do Jaeger..."
kubectl port-forward -n $NAMESPACE svc/jaeger-collector 14269:14269 > /dev/null 2>&1 &
PF_JAEGER_METRICS_PID=$!
sleep 3

JAEGER_RECEIVED=$(curl -s http://localhost:14269/metrics | grep 'jaeger_collector_spans_received_total' | awk '{sum+=$2} END {print sum}' || echo "0")

kill $PF_JAEGER_METRICS_PID 2>/dev/null

if [ -n "$JAEGER_RECEIVED" ] && [ "$JAEGER_RECEIVED" != "0" ]; then
  success "Jaeger Collector recebeu $JAEGER_RECEIVED spans"
else
  warning "Jaeger Collector ainda não recebeu spans (pode ser normal se sem tráfego)"
fi

# 6. Teste end-to-end: enviar trace e verificar no Jaeger
log "[6/6] Teste E2E: enviando trace de teste..."
TRACE_ID=$(openssl rand -hex 16)
SPAN_ID=$(openssl rand -hex 8)
INTENT_ID="test-connectivity-$(uuidgen)"

# Port-forward OTEL Collector
kubectl port-forward -n $NAMESPACE svc/neural-hive-otel-collector 4318:4318 > /dev/null 2>&1 &
PF_OTEL_PID=$!
sleep 3

# Enviar trace
curl -s -X POST http://localhost:4318/v1/traces \
  -H "Content-Type: application/json" \
  -H "x-neural-hive-intent-id: $INTENT_ID" \
  -d '{
    "resourceSpans": [{
      "resource": {
        "attributes": [{
          "key": "service.name",
          "value": {"stringValue": "connectivity-test"}
        }]
      },
      "scopeSpans": [{
        "spans": [{
          "traceId": "'$TRACE_ID'",
          "spanId": "'$SPAN_ID'",
          "name": "connectivity-test-operation",
          "kind": 1,
          "startTimeUnixNano": "'$(($(date +%s%N)))'",
          "endTimeUnixNano": "'$(($(date +%s%N) + 1000000000))'",
          "attributes": [{
            "key": "neural.hive.intent.id",
            "value": {"stringValue": "'$INTENT_ID'"}
          }]
        }]
      }]
    }]
  }' > /dev/null

kill $PF_OTEL_PID 2>/dev/null

log "Aguardando 35s para tail sampling processar..."
sleep 35

# Verificar no Jaeger
kubectl port-forward -n $NAMESPACE svc/jaeger-query 16686:16686 > /dev/null 2>&1 &
PF_JAEGER_PID=$!
sleep 3

TRACE_FOUND=$(curl -s "http://localhost:16686/api/traces?service=connectivity-test&tag=neural.hive.intent.id:$INTENT_ID" | jq -r '.data[0].traceID // "not_found"')

kill $PF_JAEGER_PID 2>/dev/null

if [ "$TRACE_FOUND" != "not_found" ]; then
  success "Trace E2E encontrado no Jaeger (traceID: $TRACE_FOUND)"
  success "Conectividade OTEL → Jaeger validada com sucesso!"
  exit 0
else
  error "Trace E2E não encontrado no Jaeger"
  warning "Possíveis causas:"
  warning "  - Tail sampling descartou o trace (probabilidade baixa)"
  warning "  - Delay na indexação do Elasticsearch"
  warning "  - Problema na exportação OTEL → Jaeger"
  exit 1
fi
