#!/bin/bash
set -e

# ============================================================================
# AVISO DE DEPRECACAO
# Este script sera descontinuado em breve.
# Use o novo CLI unificado: ml.sh train --all
# ============================================================================
echo ""
echo "AVISO: Este script sera descontinuado."
echo "       Use o novo CLI unificado: ml.sh train --all"
echo ""
sleep 2

echo "============================================="
echo "Neural Hive - Model Training Pipeline"
echo "============================================="
echo ""

# Configurações
MLFLOW_TRACKING_URI=${MLFLOW_TRACKING_URI:-"http://mlflow:5000"}
MONGODB_URI=${MONGODB_URI:-"mongodb://mongodb.data-layer:27017"}
MODEL_TYPE=${MODEL_TYPE:-"random_forest"}
HYPERPARAMETER_TUNING=${HYPERPARAMETER_TUNING:-"false"}
PROMOTE_IF_BETTER=${PROMOTE_IF_BETTER:-"true"}
DATASET_DIR=${DATASET_DIR:-"/data/training"}
ALLOW_SYNTHETIC_FALLBACK=${ALLOW_SYNTHETIC_FALLBACK:-"auto"}
REAL_DATA_DAYS=${REAL_DATA_DAYS:-90}
MIN_REAL_SAMPLES=${MIN_REAL_SAMPLES:-1000}

# Exportar variáveis de ambiente para que sejam visíveis aos processos Python
export MLFLOW_TRACKING_URI
export MONGODB_URI
export ALLOW_SYNTHETIC_FALLBACK
export REAL_DATA_DAYS
export MIN_REAL_SAMPLES
export DATASET_DIR
export TRAINING_DATASET_PATH="${DATASET_DIR}/specialist_{specialist_type}_base.parquet"

echo "📋 Configuração:"
echo "   MLflow URI: $MLFLOW_TRACKING_URI"
echo "   MongoDB URI: $MONGODB_URI"
echo "   Model Type: $MODEL_TYPE"
echo "   Hyperparameter Tuning: $HYPERPARAMETER_TUNING"
echo "   Promote If Better: $PROMOTE_IF_BETTER"
echo "   Dataset Directory: $DATASET_DIR"
echo "   Allow Synthetic Fallback: $ALLOW_SYNTHETIC_FALLBACK"
echo "   Real Data Days: $REAL_DATA_DAYS"
echo "   Min Real Samples: $MIN_REAL_SAMPLES"
echo ""

# Pre-flight checks
echo "🔍 Executando verificações pré-treinamento..."
echo ""

echo "   Verificando conectividade MLflow..."
if curl -f "$MLFLOW_TRACKING_URI/health" > /dev/null 2>&1; then
    echo "   ✅ MLflow conectado"
else
    echo "   ❌ MLflow não acessível em $MLFLOW_TRACKING_URI"
    exit 1
fi

echo "   Verificando conectividade MongoDB..."
if mongosh "$MONGODB_URI" --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
    echo "   ✅ MongoDB conectado"
else
    echo "   ⚠️  Warning: MongoDB não disponível (feedback não será incluído)"
fi

echo "   Verificando datasets..."

# Lista de especialistas para validação
SPECIALISTS_TO_CHECK=("technical" "business" "behavior" "evolution" "architecture")
EXPECTED_COUNT=${#SPECIALISTS_TO_CHECK[@]}
FOUND_COUNT=0
MISSING_SPECIALISTS=()
SCHEMA_VALID=true

# Verificar existência de cada dataset
for specialist in "${SPECIALISTS_TO_CHECK[@]}"; do
    DATASET_FILE="$DATASET_DIR/specialist_${specialist}_base.parquet"
    if [ -f "$DATASET_FILE" ]; then
        FOUND_COUNT=$((FOUND_COUNT + 1))
    else
        MISSING_SPECIALISTS+=("$specialist")
    fi
done

echo "   Datasets encontrados: $FOUND_COUNT/$EXPECTED_COUNT"

# Se ALLOW_SYNTHETIC_FALLBACK=false, todos os datasets devem existir
if [ "${ALLOW_SYNTHETIC_FALLBACK,,}" = "false" ]; then
    if [ $FOUND_COUNT -lt $EXPECTED_COUNT ]; then
        echo "   ❌ ERRO: ALLOW_SYNTHETIC_FALLBACK=false mas faltam datasets"
        echo "   ❌ Specialists sem dataset: ${MISSING_SPECIALISTS[*]}"
        echo "   Execute ./generate_all_datasets.sh para gerar os datasets faltantes"
        exit 1
    fi
fi

# Se encontramos pelo menos um dataset, validar schemas
if [ $FOUND_COUNT -gt 0 ]; then
    # Listar specialists com datasets
    FOUND_SPECIALISTS=()
    for specialist in "${SPECIALISTS_TO_CHECK[@]}"; do
        DATASET_FILE="$DATASET_DIR/specialist_${specialist}_base.parquet"
        if [ -f "$DATASET_FILE" ]; then
            FOUND_SPECIALISTS+=("$specialist")
        fi
    done
    echo "   ✅ Datasets encontrados para: ${FOUND_SPECIALISTS[*]}"

    if [ ${#MISSING_SPECIALISTS[@]} -gt 0 ]; then
        if [ "${ALLOW_SYNTHETIC_FALLBACK,,}" = "true" ]; then
            echo "   ⚠️  Datasets não encontrados para: ${MISSING_SPECIALISTS[*]} (usará fallback sintético)"
        fi
    fi

    # Validar schema de datasets existentes
    echo "   Validando schema de datasets..."
    for specialist in "${SPECIALISTS_TO_CHECK[@]}"; do
        DATASET_FILE="$DATASET_DIR/specialist_${specialist}_base.parquet"
        if [ -f "$DATASET_FILE" ]; then
            # Validar schema usando Python
            if ! python -c "
import pandas as pd
import sys
sys.path.insert(0, '$(dirname "$0")/..')
from feature_store.feature_definitions import get_feature_names

df = pd.read_parquet('$DATASET_FILE')
expected = set(get_feature_names() + ['label'])
actual = set(df.columns)

if expected != actual:
    missing = expected - actual
    extra = actual - expected
    print(f'Schema mismatch in $specialist dataset')
    if missing:
        print(f'   Missing: {missing}')
    if extra:
        print(f'   Extra: {extra}')
    sys.exit(1)
else:
    print(f'Schema valid for $specialist ({len(df)} samples, {len(df.columns)-1} features)')
" 2>/dev/null; then
                echo "   ❌ Schema validation failed for $specialist"
                SCHEMA_VALID=false
            fi
        fi
    done

    if [ "$SCHEMA_VALID" = false ]; then
        echo "   ❌ Schema validation failed. Run generate_all_datasets.sh to regenerate."
        exit 1
    fi
    echo "   ✅ Schema validation passed"
else
    # Nenhum dataset encontrado
    if [ "${ALLOW_SYNTHETIC_FALLBACK,,}" = "false" ]; then
        echo "   ❌ Nenhum dataset encontrado em $DATASET_DIR e ALLOW_SYNTHETIC_FALLBACK=false"
        exit 1
    else
        echo "   ⚠️  Nenhum dataset encontrado em $DATASET_DIR; usando fallback sintético para todos os specialists"
    fi
fi

echo ""
echo "============================================="
echo "🚀 Iniciando treinamento de todos os especialistas"
echo "============================================="
echo ""

# Lista de especialistas
SPECIALISTS=("technical" "business" "behavior" "evolution" "architecture")

# Loop de treinamento
for specialist in "${SPECIALISTS[@]}"; do
    echo "📊 Treinando modelo para especialista: $specialist"
    echo ""

    if python train_specialist_model.py \
        --specialist-type "$specialist" \
        --model-type "$MODEL_TYPE" \
        --hyperparameter-tuning "$HYPERPARAMETER_TUNING" \
        --promote-if-better "$PROMOTE_IF_BETTER" \
        --allow-synthetic-fallback "$ALLOW_SYNTHETIC_FALLBACK" \
        --real-data-days "$REAL_DATA_DAYS" \
        --min-real-samples "$MIN_REAL_SAMPLES"; then
        echo ""
        echo "   ✅ Modelo treinado e registrado para $specialist"
        echo ""
    else
        echo ""
        echo "   ❌ Falha ao treinar especialista $specialist"
        exit 1
    fi

    # Aguardar entre specialists para evitar contenção no MLflow
    if [ "$specialist" != "architecture" ]; then
        echo "   ⏳ Aguardando 2 segundos..."
        sleep 2
        echo ""
    fi
done

echo ""
echo "============================================="
echo "✅ Todos os 5 modelos de especialistas foram treinados com sucesso!"
echo "============================================="
echo ""

echo "📊 Modelos registrados:"
echo ""
curl -s "$MLFLOW_TRACKING_URI/api/2.0/mlflow/registered-models/list" | \
    jq '.registered_models[] | select(.name | contains("evaluator")) | {name: .name, latest_version: .latest_versions[0].version}'

echo ""
echo "🔄 Próximos passos:"
echo "   1. Validar modelos: ./validate_models_loaded.sh"
echo "   2. Reiniciar pods de especialistas para carregar novos modelos:"
echo "      kubectl rollout restart deployment -n semantic-translation -l app.kubernetes.io/component=specialist"
echo ""
