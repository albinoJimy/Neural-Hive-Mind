#!/bin/bash
#
# Analisar latência por fase de um trace
#
# Uso:
#   ./scripts/observability/analyze-trace-latency.sh <trace-id>
#
# Variáveis de ambiente:
#   JAEGER_URL: URL do Jaeger Query (default: http://jaeger-query:16686)
#

set -euo pipefail

TRACE_ID=${1:-}
JAEGER_URL="${JAEGER_URL:-http://jaeger-query:16686}"

if [ -z "$TRACE_ID" ]; then
    echo "Uso: $0 <trace-id>"
    echo ""
    echo "Exemplo:"
    echo "  $0 abc123def456..."
    echo "  JAEGER_URL=http://localhost:16686 $0 abc123def456..."
    exit 1
fi

echo "Analisando trace: $TRACE_ID"
echo "Jaeger URL: $JAEGER_URL"
echo "================================"
echo ""

# Buscar trace
TRACE_DATA=$(curl -s "$JAEGER_URL/api/traces/$TRACE_ID")

if [ "$(echo "$TRACE_DATA" | jq '.data | length')" -eq 0 ]; then
    echo "Trace não encontrado: $TRACE_ID"
    exit 1
fi

# Extrair informações básicas
SPAN_COUNT=$(echo "$TRACE_DATA" | jq '.data[0].spans | length')
SERVICES=$(echo "$TRACE_DATA" | jq -r '.data[0].processes | to_entries[] | .value.serviceName' | sort -u | wc -l)

echo "Spans: $SPAN_COUNT"
echo "Serviços: $SERVICES"
echo ""

# Listar spans por duração (mais lentos primeiro)
echo "Latência por operação (ordenado por duração):"
echo "----------------------------------------------"
echo "$TRACE_DATA" | jq -r '.data[0] |
    .processes as $procs |
    .spans | sort_by(-.duration)[] |
    "\($procs[.processID].serviceName).\(.operationName): \((.duration / 1000) | round)ms"'

echo ""
echo "Top 5 spans mais lentos:"
echo "------------------------"
echo "$TRACE_DATA" | jq -r '.data[0] |
    .processes as $procs |
    .spans | sort_by(-.duration) | .[0:5][] |
    "  \($procs[.processID].serviceName).\(.operationName): \((.duration / 1000) | round)ms"'

# Verificar erros
ERRORS=$(echo "$TRACE_DATA" | jq '[.data[0].spans[] | select(.tags[] | select(.key=="error" and .value==true))] | length')

echo ""
if [ "$ERRORS" -gt 0 ]; then
    echo "⚠️  Encontrados $ERRORS span(s) com erro:"
    echo "$TRACE_DATA" | jq -r '.data[0] |
        .processes as $procs |
        .spans[] |
        select(.tags[] | select(.key=="error" and .value==true)) |
        "  ❌ \($procs[.processID].serviceName).\(.operationName)"'
else
    echo "✓ Nenhum erro encontrado no trace"
fi

# Calcular duração total
TOTAL_DURATION=$(echo "$TRACE_DATA" | jq '.data[0].spans | map(.duration) | max / 1000 | round')
echo ""
echo "Duração total do trace: ${TOTAL_DURATION}ms"
