#!/bin/bash
# Script para gerar os datasets faltantes com DeepSeek
# Execute: ./generate_remaining_datasets.sh

set -e

cd /jimy/Neural-Hive-Mind/ml_pipelines/training

# Configurações
export LLM_PROVIDER=deepseek
export LLM_MODEL=deepseek-chat
export LLM_API_KEY=sk-6cd0e5de616c4d5bb7232fe87f8c9bfd
export PYTHONPATH="/jimy/Neural-Hive-Mind/libraries/python:/jimy/Neural-Hive-Mind/ml_pipelines:$PYTHONPATH"
export MIN_QUALITY_SCORE=0.5

# Número de samples por especialista (ajuste conforme necessário)
NUM_SAMPLES=20

echo "=============================================="
echo "Neural Hive - Geração de Datasets com DeepSeek"
echo "=============================================="
echo ""
echo "Configuração:"
echo "  Provider: $LLM_PROVIDER"
echo "  Model: $LLM_MODEL"
echo "  Samples: $NUM_SAMPLES por especialista"
echo ""

# Verificar datasets existentes
echo "Status atual dos datasets:"
for f in data/specialist_*_base.parquet; do
    if [ -f "$f" ]; then
        count=$(python3 -c "import pandas as pd; df=pd.read_parquet('$f'); print(df.shape[0])" 2>/dev/null || echo "0")
        echo "  $(basename $f): $count samples"
    fi
done
echo ""

# Lista de especialistas para gerar
SPECIALISTS=("behavior" "evolution" "architecture")

for specialist in "${SPECIALISTS[@]}"; do
    output_file="data/specialist_${specialist}_base.parquet"

    # Verificar se já existe com samples suficientes
    if [ -f "$output_file" ]; then
        existing=$(python3 -c "import pandas as pd; df=pd.read_parquet('$output_file'); print(df.shape[0])" 2>/dev/null || echo "0")
        if [ "$existing" -ge 15 ]; then
            echo "✓ Dataset $specialist já tem $existing samples, pulando..."
            continue
        fi
    fi

    echo ""
    echo ">>> Gerando dataset para: $specialist"
    echo "    Output: $output_file"
    echo "    Samples: $NUM_SAMPLES"
    echo ""

    python3 generate_training_datasets.py \
        --specialist-type "$specialist" \
        --num-samples "$NUM_SAMPLES" \
        --output-path "$output_file" \
        --llm-provider deepseek \
        --llm-model deepseek-chat \
        --min-quality-score 0.5

    if [ $? -eq 0 ]; then
        echo "✓ Dataset $specialist gerado com sucesso!"
    else
        echo "✗ Erro ao gerar dataset $specialist"
    fi
done

echo ""
echo "=============================================="
echo "Geração finalizada!"
echo ""
echo "Status final dos datasets:"
for f in data/specialist_*_base.parquet; do
    if [ -f "$f" ]; then
        count=$(python3 -c "import pandas as pd; df=pd.read_parquet('$f'); print(df.shape[0])" 2>/dev/null || echo "0")
        echo "  $(basename $f): $count samples"
    fi
done
echo "=============================================="
