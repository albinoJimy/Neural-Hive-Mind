#!/bin/bash
set -e

# ============================================================================
# AVISO DE DEPRECACAO
# Este script sera descontinuado em breve.
# Use o novo CLI unificado: ml.sh generate-dataset --all
# ============================================================================
echo ""
echo "AVISO: Este script sera descontinuado."
echo "       Use o novo CLI unificado: ml.sh generate-dataset --all"
echo ""
sleep 2

echo "============================================="
echo "Neural Hive - Dataset Generation Pipeline"
echo "============================================="
echo ""

# Configuracoes
LLM_PROVIDER=${LLM_PROVIDER:-"openai"}
LLM_MODEL=${LLM_MODEL:-"gpt-4"}
NUM_SAMPLES=${NUM_SAMPLES:-1000}
OUTPUT_DIR=${OUTPUT_DIR:-"/data/training"}
MIN_QUALITY_SCORE=${MIN_QUALITY_SCORE:-0.6}

echo "Configuracao:"
echo "   LLM Provider: $LLM_PROVIDER"
echo "   LLM Model: $LLM_MODEL"
echo "   Samples per Specialist: $NUM_SAMPLES"
echo "   Output Directory: $OUTPUT_DIR"
echo "   Min Quality Score: $MIN_QUALITY_SCORE"
echo ""

# Criar diretorio de saida
mkdir -p "$OUTPUT_DIR"

# Lista de especialistas
SPECIALISTS=("technical" "business" "behavior" "evolution" "architecture")

# Loop de geracao
for specialist in "${SPECIALISTS[@]}"; do
    echo "Gerando dataset para especialista: $specialist"
    echo ""

    OUTPUT_FILE="$OUTPUT_DIR/specialist_${specialist}_base.parquet"

    if python generate_training_datasets.py \
        --specialist-type "$specialist" \
        --num-samples "$NUM_SAMPLES" \
        --output-path "$OUTPUT_FILE" \
        --llm-provider "$LLM_PROVIDER" \
        --llm-model "$LLM_MODEL" \
        --min-quality-score "$MIN_QUALITY_SCORE"; then
        echo ""
        echo "   Dataset gerado: $OUTPUT_FILE"

        # Validar Parquet (shape e colunas basicas)
        if python -c "import pandas as pd; df=pd.read_parquet('$OUTPUT_FILE'); print(f'   Shape: {df.shape}'); print(f'   Columns: {list(df.columns)[:5]}...')"; then
            echo "   Validacao Parquet basica OK"
        else
            echo "   Validacao Parquet FALHOU"
            exit 1
        fi

        # Validar schema de features (deve corresponder exatamente ao feature_definitions.py)
        echo "   Validando schema de features..."
        if python -c "
import pandas as pd
import sys
sys.path.insert(0, '$(dirname "$0")/..')
from feature_store.feature_definitions import get_feature_names

df = pd.read_parquet('$OUTPUT_FILE')
expected = set(get_feature_names() + ['label'])
actual = set(df.columns)

if expected != actual:
    missing = expected - actual
    extra = actual - expected
    print(f'   ERRO: Schema mismatch para $specialist')
    if missing:
        print(f'   Missing: {missing}')
    if extra:
        print(f'   Extra: {extra}')
    sys.exit(1)
else:
    print(f'   Schema OK: {len(df.columns)-1} features + label')
"; then
            echo "   Validacao de schema OK"
        else
            echo "   Validacao de schema FALHOU"
            exit 1
        fi
        echo ""
    else
        echo ""
        echo "   Falha ao gerar dataset para $specialist"
        exit 1
    fi

    # Aguardar entre specialists para evitar rate limit LLM
    if [ "$specialist" != "architecture" ]; then
        echo "   Aguardando 5 segundos..."
        sleep 5
        echo ""
    fi
done

echo ""
echo "============================================="
echo "Todos os 5 datasets foram gerados com sucesso!"
echo "============================================="
echo ""

echo "Datasets gerados:"
ls -lh "$OUTPUT_DIR"/specialist_*_base.parquet

echo ""
echo "Proximos passos:"
echo "   1. Treinar modelos: ./train_all_specialists.sh"
echo "   2. Validar modelos: ./validate_models_loaded.sh"
echo ""
