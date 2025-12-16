#!/bin/bash
set -e

echo "🔍 Validando integração ML no Orchestrator..."

ORCHESTRATOR_URL=${ORCHESTRATOR_URL:-"http://localhost:8000"}

# Health check ML
echo "1. Verificando /health/ml..."
RESPONSE=$(curl -s "$ORCHESTRATOR_URL/health/ml")
STATUS=$(echo "$RESPONSE" | jq -r '.status')

if [ "$STATUS" = "healthy" ]; then
    echo "✅ ML health check passou"
    
    # Verificar preditores
    SCHEDULING_LOADED=$(echo "$RESPONSE" | jq -r '.predictors.scheduling_predictor.loaded')
    LOAD_LOADED=$(echo "$RESPONSE" | jq -r '.predictors.load_predictor.loaded // empty')
    ANOMALY_LOADED=$(echo "$RESPONSE" | jq -r '.predictors.anomaly_detector.loaded')
    
    echo "   - SchedulingPredictor: $SCHEDULING_LOADED"
    if [ -n "$LOAD_LOADED" ]; then
        echo "   - LoadPredictor: $LOAD_LOADED"
    else
        echo "   - LoadPredictor: (não informado)"
    fi
    echo "   - AnomalyDetector: $ANOMALY_LOADED"
    
    if [ "$SCHEDULING_LOADED" = "true" ] && [ "$ANOMALY_LOADED" = "true" ]; then
        echo "✅ Preditores críticos carregados (scheduling e anomaly)"
        if [ "$LOAD_LOADED" != "true" ]; then
            echo "ℹ️  LoadPredictor ausente ou desabilitado - continuando"
        fi
    else
        echo "⚠️  Preditores críticos ausentes"
        exit 1
    fi
else
    echo "❌ ML health check falhou: $STATUS"
    exit 1
fi

# Listar modelos
echo ""
echo "2. Verificando /api/v1/ml/models..."
MODELS=$(curl -s "$ORCHESTRATOR_URL/api/v1/ml/models")
MODEL_COUNT=$(echo "$MODELS" | jq '.models | length')

echo "✅ $MODEL_COUNT modelos registrados"
echo "$MODELS" | jq -r '.models[] | \"   - \\(.name) (\\(.stage)) - \\(.integration_status)\"'

echo ""
echo "✅ Validação concluída com sucesso"
