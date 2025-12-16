#!/bin/bash

echo "============================================="
echo "🔍 Neural Hive - Model Loading Validation"
echo "============================================="
echo ""

# Configurações
NAMESPACE=${NAMESPACE:-"semantic-translation"}
MLFLOW_URI=${MLFLOW_URI:-"http://mlflow.mlflow:5000"}

echo "📋 Configuração:"
echo "   Namespace: $NAMESPACE"
echo "   MLflow URI: $MLFLOW_URI"
echo ""

# Contadores
SUCCESS_COUNT=0
FAILURE_COUNT=0

# Lista de especialistas
SPECIALISTS=("technical" "business" "behavior" "evolution" "architecture")

echo "============================================="
echo "📊 Verificando modelos registrados no MLflow"
echo "============================================="
echo ""

for specialist in "${SPECIALISTS[@]}"; do
    MODEL_NAME="${specialist}-evaluator"
    echo "🔍 Verificando modelo: $MODEL_NAME"

    # Query MLflow API
    RESPONSE=$(curl -s "$MLFLOW_URI/api/2.0/mlflow/registered-models/get?name=$MODEL_NAME")

    # Verificar se modelo existe
    if echo "$RESPONSE" | jq -e '.registered_model' > /dev/null 2>&1; then
        # Verificar se tem versão em Production
        PRODUCTION_VERSION=$(echo "$RESPONSE" | jq -r '.registered_model.latest_versions[] | select(.current_stage == "Production") | .version' 2>/dev/null)

        if [ -n "$PRODUCTION_VERSION" ]; then
            echo "   ✅ Modelo $MODEL_NAME encontrado em Production (versão $PRODUCTION_VERSION)"
        else
            echo "   ⚠️  Modelo $MODEL_NAME encontrado mas não está em Production"
        fi
    else
        echo "   ❌ Modelo $MODEL_NAME não encontrado"
    fi
    echo ""
done

echo "============================================="
echo "🔍 Verificando health dos pods de especialistas"
echo "============================================="
echo ""

for specialist in "${SPECIALISTS[@]}"; do
    echo "🔍 Verificando especialista: $specialist"

    # Obter pod name
    POD=$(kubectl get pods -n "$NAMESPACE" -l "app=specialist-${specialist}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -z "$POD" ]; then
        echo "   ❌ Pod não encontrado para specialist-${specialist}"
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
        echo ""
        continue
    fi

    echo "   Pod: $POD"

    # Verificar status do pod
    POD_PHASE=$(kubectl get pod -n "$NAMESPACE" "$POD" -o jsonpath='{.status.phase}' 2>/dev/null)
    echo "   Status: $POD_PHASE"

    if [ "$POD_PHASE" != "Running" ]; then
        echo "   ❌ Pod não está rodando"
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
        echo ""
        continue
    fi

    # Verificar readiness
    POD_READY=$(kubectl get pod -n "$NAMESPACE" "$POD" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
    echo "   Ready: $POD_READY"

    if [ "$POD_READY" != "True" ]; then
        echo "   ⚠️  Pod não está ready"
    fi

    # Query health endpoint
    echo "   Consultando /status..."
    HEALTH_RESPONSE=$(kubectl exec -n "$NAMESPACE" "$POD" -- curl -s localhost:8000/status 2>/dev/null)

    if [ $? -eq 0 ]; then
        # Verificar se existe campo details antes de parsear
        if ! echo "$HEALTH_RESPONSE" | jq -e '.details' > /dev/null 2>&1; then
            echo "   ❌ Payload inesperado: campo 'details' não encontrado no /status"
            if [ -n "$HEALTH_RESPONSE" ]; then
                echo "   🔍 Debug - JSON bruto recebido:"
                echo "$HEALTH_RESPONSE" | head -c 500
                echo ""
            fi
            FAILURE_COUNT=$((FAILURE_COUNT + 1))
            echo ""
            continue
        fi

        # Parse resposta JSON (agora model_loaded está em details.model_loaded)
        SPECIALIST_TYPE=$(echo "$HEALTH_RESPONSE" | jq -r '.specialist_type // "unknown"' 2>/dev/null)
        STATUS=$(echo "$HEALTH_RESPONSE" | jq -r '.status // "UNKNOWN"' 2>/dev/null)
        MODEL_LOADED=$(echo "$HEALTH_RESPONSE" | jq -r '.details.model_loaded // "unknown"' 2>/dev/null)
        MLFLOW_CONNECTED=$(echo "$HEALTH_RESPONSE" | jq -r '.details.mlflow_connected // "unknown"' 2>/dev/null)
        LEDGER_CONNECTED=$(echo "$HEALTH_RESPONSE" | jq -r '.details.ledger_connected // "unknown"' 2>/dev/null)

        echo "   Specialist Type: $SPECIALIST_TYPE"
        echo "   Status: $STATUS"
        echo "   MLflow Connected: $MLFLOW_CONNECTED"
        echo "   Ledger Connected: $LEDGER_CONNECTED"
        echo "   Model Loaded: $MODEL_LOADED"

        # Avisar se valores foram retornados como "unknown"
        if [ "$STATUS" = "UNKNOWN" ]; then
            echo "   ⚠️  Status não foi retornado pelo endpoint - payload pode estar incompleto"
        fi

        # Verificar degraded_reasons se existir
        DEGRADED_REASONS=$(echo "$HEALTH_RESPONSE" | jq -r '.details.degraded_reasons[]?' 2>/dev/null)
        if [ -n "$DEGRADED_REASONS" ]; then
            echo "   ⚠️  Degraded reasons: $DEGRADED_REASONS"
        fi

        # Model loaded pode ser string "True" ou "False" (retornado por health_check)
        if [ "$MODEL_LOADED" = "True" ] || [ "$MODEL_LOADED" = "true" ]; then
            echo "   ✅ Especialista $specialist carregou modelo com sucesso"
            SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        elif [ "$MODEL_LOADED" = "unknown" ]; then
            echo "   ❌ Especialista $specialist: campo model_loaded não foi retornado"
            echo "   🔍 Diagnóstico:"
            echo "      - Campo details.model_loaded ausente ou null no payload"
            echo "      - Verifique se specialist.health_check() está retornando model_loaded"
            FAILURE_COUNT=$((FAILURE_COUNT + 1))
        else
            echo "   ❌ Especialista $specialist falhou ao carregar modelo"
            echo "   🔍 Diagnóstico:"

            # Fornecer diagnóstico específico
            if [ "$STATUS" != "SERVING" ]; then
                echo "      - Status não está SERVING (atual: $STATUS)"
            fi

            if [ "$MLFLOW_CONNECTED" = "False" ] || [ "$MLFLOW_CONNECTED" = "false" ]; then
                echo "      - MLflow não está conectado - verifique se MLflow está disponível"
                echo "      - Comando: kubectl logs -n mlflow -l app=mlflow --tail=20"
            elif [ "$MLFLOW_CONNECTED" = "unknown" ]; then
                echo "      - Campo mlflow_connected não foi retornado"
            fi

            if [ "$MODEL_LOADED" = "False" ] || [ "$MODEL_LOADED" = "false" ]; then
                echo "      - Modelo não foi carregado - possíveis causas:"
                echo "        * Modelo não existe no MLflow para $specialist-evaluator"
                echo "        * Modelo não está em stage Production"
                echo "        * Erro ao carregar modelo (verificar logs do pod)"
            fi

            FAILURE_COUNT=$((FAILURE_COUNT + 1))
        fi
    else
        echo "   ❌ Falha ao consultar endpoint /status"
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
    fi

    echo ""
done

echo "============================================="
echo "📊 Resumo da Validação"
echo "============================================="
echo ""

if [ $SUCCESS_COUNT -eq 5 ]; then
    echo "✅ $SUCCESS_COUNT/5 especialistas carregaram modelos com sucesso"
    echo ""
    exit 0
else
    echo "⚠️  $SUCCESS_COUNT/5 especialistas carregaram modelos com sucesso"
    echo "❌ $FAILURE_COUNT especialistas falharam"
    echo ""
    echo "🔧 Para investigar falhas, verifique os logs:"
    for specialist in "${SPECIALISTS[@]}"; do
        echo "   kubectl logs -n $NAMESPACE -l app=specialist-${specialist} --tail=50"
    done
    echo ""
    exit 1
fi
