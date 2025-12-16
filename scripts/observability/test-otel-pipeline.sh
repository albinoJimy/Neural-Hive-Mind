#!/bin/bash
# Testar pipeline OTEL Collector com trace sintético

set -euo pipefail

NAMESPACE="${NAMESPACE:-observability}"
INTENT_ID="test-intent-$(uuidgen)"
PLAN_ID="test-plan-$(uuidgen)"
USER_ID="test-user-123"
METRICS_PORT="${METRICS_PORT:-8888}"
OTLP_HTTP_PORT="${OTLP_HTTP_PORT:-4318}"
ZPAGES_PORT="${ZPAGES_PORT:-55679}"

cleanup() {
  [ -n "${PF_METRICS_PID:-}" ] && kill $PF_METRICS_PID 2>/dev/null || true
  [ -n "${PF_OTLP_PID:-}" ] && kill $PF_OTLP_PID 2>/dev/null || true
  [ -n "${PF_ZPAGES_PID:-}" ] && kill $PF_ZPAGES_PID 2>/dev/null || true
  [ -n "${PF_JAEGER_PID:-}" ] && kill $PF_JAEGER_PID 2>/dev/null || true
}
trap cleanup EXIT

metric_value() {
  local metric="$1"
  curl -s http://localhost:$METRICS_PORT/metrics | awk -v m="$metric" '$1==m {print $2}' | head -n1
}

echo "Iniciando validação do pipeline OTEL Collector no namespace $NAMESPACE"

# Port-forward métricas
kubectl port-forward -n $NAMESPACE svc/neural-hive-otel-collector $METRICS_PORT:$METRICS_PORT >/dev/null 2>&1 &
PF_METRICS_PID=$!
sleep 3

RECEIVER_BEFORE=$(metric_value 'otelcol_receiver_accepted_spans{receiver="otlp"}')
EXPORTER_BEFORE=$(metric_value 'otelcol_exporter_sent_spans{exporter="jaeger"}')
[ -z "$RECEIVER_BEFORE" ] && RECEIVER_BEFORE=0
[ -z "$EXPORTER_BEFORE" ] && EXPORTER_BEFORE=0

# Port-forward OTLP receiver
kubectl port-forward -n $NAMESPACE svc/neural-hive-otel-collector $OTLP_HTTP_PORT:$OTLP_HTTP_PORT >/dev/null 2>&1 &
PF_OTLP_PID=$!
sleep 3

# Enviar trace via OTLP HTTP com atributos Neural Hive
curl -X POST http://localhost:$OTLP_HTTP_PORT/v1/traces \
  -H "Content-Type: application/json" \
  -H "x-neural-hive-intent-id: $INTENT_ID" \
  -H "x-neural-hive-plan-id: $PLAN_ID" \
  -H "x-neural-hive-user-id: $USER_ID" \
  -H "x-neural-hive-domain: test" \
  -d '{
    "resourceSpans": [{
      "resource": {
        "attributes": [{
          "key": "service.name",
          "value": {"stringValue": "test-service"}
        }]
      },
      "scopeSpans": [{
        "spans": [{
          "traceId": "'$(openssl rand -hex 16)'",
          "spanId": "'$(openssl rand -hex 8)'",
          "name": "test-operation",
          "kind": 1,
          "startTimeUnixNano": "'$(($(date +%s%N)))'",
          "endTimeUnixNano": "'$(($(date +%s%N) + 1000000000))'",
          "attributes": [{
            "key": "neural.hive.intent.id",
            "value": {"stringValue": "'$INTENT_ID'"}
          }, {
            "key": "neural.hive.plan.id",
            "value": {"stringValue": "'$PLAN_ID'"}
          }]
        }]
      }]
    }]
  }'

kill $PF_OTLP_PID 2>/dev/null

echo "Trace enviado com intent_id=$INTENT_ID, plan_id=$PLAN_ID"
echo "Aguardar 30s para tail sampling processar..."
sleep 30

RECEIVER_AFTER=$(metric_value 'otelcol_receiver_accepted_spans{receiver="otlp"}')
EXPORTER_AFTER=$(metric_value 'otelcol_exporter_sent_spans{exporter="jaeger"}')
[ -z "$RECEIVER_AFTER" ] && RECEIVER_AFTER=$RECEIVER_BEFORE
[ -z "$EXPORTER_AFTER" ] && EXPORTER_AFTER=$EXPORTER_BEFORE

if [ "$RECEIVER_AFTER" -le "$RECEIVER_BEFORE" ]; then
  echo "✗ Métrica otelcol_receiver_accepted_spans não incrementou (antes=$RECEIVER_BEFORE, depois=$RECEIVER_AFTER)"
  exit 1
fi

if [ "$EXPORTER_AFTER" -le "$EXPORTER_BEFORE" ]; then
  echo "✗ Métrica otelcol_exporter_sent_spans (jaeger) não incrementou (antes=$EXPORTER_BEFORE, depois=$EXPORTER_AFTER)"
  exit 1
fi

echo "✓ Métricas do pipeline incrementaram (receiver $RECEIVER_BEFORE -> $RECEIVER_AFTER, exporter $EXPORTER_BEFORE -> $EXPORTER_AFTER)"

# Checar zpages para presença dos atributos
kubectl port-forward -n $NAMESPACE svc/neural-hive-otel-collector $ZPAGES_PORT:$ZPAGES_PORT >/dev/null 2>&1 &
PF_ZPAGES_PID=$!
sleep 3

if curl -s http://localhost:$ZPAGES_PORT/debug/tracez | grep -q "$INTENT_ID"; then
  echo "✓ zpages apresenta o intent_id esperado (processors baggage/span + attributes/neural_hive atuando)"
else
  echo "✗ zpages não exibiu o intent_id; verifique processors baggage/span e attributes/neural_hive"
fi

# Verificar no Jaeger
kubectl port-forward -n $NAMESPACE svc/jaeger-query 16686:16686 >/dev/null 2>&1 &
PF_JAEGER_PID=$!
sleep 3

TRACE_FOUND=$(curl -s "http://localhost:16686/api/traces?service=test-service&tag=neural.hive.intent.id:$INTENT_ID" | jq -r '.data[0].traceID // "not_found"')

kill $PF_JAEGER_PID 2>/dev/null

if [ "$TRACE_FOUND" != "not_found" ]; then
  echo "✓ Trace encontrado no Jaeger com atributos Neural Hive"
  exit 0
else
  echo "✗ Trace não encontrado no Jaeger"
  exit 1
fi
