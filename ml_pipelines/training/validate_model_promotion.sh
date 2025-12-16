#!/bin/bash
set -e

echo "🔍 Validando promoção de modelos para Production..."

MLFLOW_URI=${MLFLOW_URI:-"http://mlflow.mlflow:5000"}
MODELS=("scheduling-predictor-xgboost" "load-predictor-60m" "load-predictor-360m" "load-predictor-1440m" "anomaly-detector-isolation_forest")

SUCCESS=0
TOTAL=${#MODELS[@]}

for model in "${MODELS[@]}"; do
    echo "Verificando $model..."
    
    RESPONSE=$(curl -s "$MLFLOW_URI/api/2.0/mlflow/registered-models/get?name=$model")
    
    PRODUCTION_VERSION=$(echo "$RESPONSE" | jq -r '.registered_model.latest_versions[] | select(.current_stage == "Production") | .version' 2>/dev/null)
    
    if [ -n "$PRODUCTION_VERSION" ]; then
        echo "✅ $model está em Production (versão $PRODUCTION_VERSION)"
        SUCCESS=$((SUCCESS + 1))
    else
        echo "❌ $model NÃO está em Production"
    fi
done

echo ""
echo "📊 Resultado: $SUCCESS/$TOTAL modelos em Production"

if [ $SUCCESS -eq $TOTAL ]; then
    echo "✅ Todos os modelos foram promovidos com sucesso"
    exit 0
else
    echo "⚠️  Alguns modelos não foram promovidos"
    exit 1
fi
