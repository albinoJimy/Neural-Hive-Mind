#!/bin/bash
echo "⚠️  AVISO: Este script foi consolidado no CLI unificado de validação."
echo "⚠️  Use: scripts/validate.sh --target <TARGET>"
echo "⚠️  Exemplo: scripts/validate.sh --target specialists"
echo ""
echo "Executando script legado..."
echo ""
set -e

echo "📊 Validando métricas Prometheus de modelos ML..."

ORCHESTRATOR_URL=${ORCHESTRATOR_URL:-"http://localhost:8000"}

# Obter métricas
METRICS=$(curl -s "$ORCHESTRATOR_URL/metrics")

# Verificar métricas específicas de ML
echo "1. Verificando métricas de predição..."
PRED_METRIC="orchestration_ml_prediction_duration_seconds"
if echo "$METRICS" | grep -q "^${PRED_METRIC}_bucket"; then
    echo "✅ ${PRED_METRIC} encontrada"
    
    BUCKETS=$(echo "$METRICS" | grep "^${PRED_METRIC}_bucket")
    P95=$(python - <<'PY'\nimport sys, re\nfrom math import inf\nbuckets = {}\ntotal = 0.0\nfor line in sys.stdin:\n    m = re.search(r'le=\"([0-9eE\\+\\-\\.Inf]+)\".*\\} ([0-9\\.]+)', line)\n    if not m:\n        continue\n    le_raw, value = m.group(1), float(m.group(2))\n    le = float('inf') if le_raw in ('+Inf', 'Inf', 'inf') else float(le_raw)\n    buckets[le] = buckets.get(le, 0.0) + value\n    total += value\nif total == 0:\n    print('')\n    sys.exit(0)\nacc = 0.0\nfor le in sorted(buckets):\n    acc += buckets[le]\n    if acc / total >= 0.95:\n        print(le)\n        break\nPY <<< "$BUCKETS")

    if [ -n "$P95" ]; then
        echo "   P95 latency bucket: ${P95}s"
        
        if [ "$P95" != "inf" ] && (( $(echo "$P95 < 0.1" | bc -l) )); then
            echo "   ✅ P95 latency < 100ms (SLO atendido)"
        else
            echo "   ⚠️  P95 latency >= 100ms (SLO não atendido)"
        fi
    else
        echo "   ⚠️  Não foi possível calcular P95 (sem buckets)"
    fi
else
    echo "⚠️  ${PRED_METRIC} não encontrada"
fi

echo ""
echo "2. Verificando métricas de anomalia..."
if echo "$METRICS" | grep -q "^orchestration_ml_anomalies_detected_total"; then
    ANOMALY_COUNT=$(echo "$METRICS" | grep "^orchestration_ml_anomalies_detected_total" | awk '{print $2}')
    echo "✅ orchestration_ml_anomalies_detected_total: $ANOMALY_COUNT"
else
    echo "⚠️  orchestration_ml_anomalies_detected_total não encontrada"
fi

echo ""
echo "3. Verificando métricas de cache..."
if echo "$METRICS" | grep -q "^orchestration_ml_prediction_cache_hits_total"; then
    CACHE_HITS=$(echo "$METRICS" | grep "^orchestration_ml_prediction_cache_hits_total" | awk '{print $2}')
    echo "✅ orchestration_ml_prediction_cache_hits_total: $CACHE_HITS"
else
    echo "⚠️  Métricas de cache não encontradas"
fi

echo ""
echo "✅ Validação de métricas concluída"
