#!/bin/bash
#
# Extrair todos os intent_ids de um período
#
# Uso:
#   ./scripts/observability/extract-intent-ids.sh [horas_atras]
#
# Variáveis de ambiente:
#   JAEGER_URL: URL do Jaeger Query (default: http://jaeger-query:16686)
#

set -euo pipefail

HOURS_AGO=${1:-1}
JAEGER_URL="${JAEGER_URL:-http://jaeger-query:16686}"

echo "Extraindo intent_ids das últimas $HOURS_AGO hora(s)..."
echo "Jaeger URL: $JAEGER_URL"
echo "================================"
echo ""

# Calcular timestamps
START_TIME=$(($(date +%s) - ($HOURS_AGO * 3600)))000000
END_TIME=$(date +%s)000000

# Buscar traces
TRACES=$(curl -s "$JAEGER_URL/api/traces?\
service=gateway-intencoes&\
start=$START_TIME&\
end=$END_TIME&\
limit=1000")

# Extrair intent_ids únicos
INTENT_IDS=$(echo "$TRACES" | jq -r '
    [.data[].spans[] |
        .tags[] |
        select(.key=="neural.hive.intent.id") |
        .value
    ] | unique | .[]' 2>/dev/null || echo "")

if [ -z "$INTENT_IDS" ]; then
    echo "Nenhum intent_id encontrado no período."
    exit 0
fi

# Contar e listar
COUNT=$(echo "$INTENT_IDS" | wc -l)
echo "Total de intent_ids únicos: $COUNT"
echo ""
echo "Intent IDs:"
echo "-----------"
echo "$INTENT_IDS"
