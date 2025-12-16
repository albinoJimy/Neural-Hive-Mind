#!/bin/bash
# Script para gerar mais samples para datasets com poucos dados
# Execute: ./generate_more_samples.sh

set -e

cd /jimy/Neural-Hive-Mind/ml_pipelines/training

# Configurações
export LLM_PROVIDER=deepseek
export LLM_MODEL=deepseek-chat
export LLM_API_KEY=sk-6cd0e5de616c4d5bb7232fe87f8c9bfd
export PYTHONPATH="/jimy/Neural-Hive-Mind/libraries/python:/jimy/Neural-Hive-Mind/ml_pipelines:$PYTHONPATH"
export MIN_QUALITY_SCORE=0.5

# Número de samples adicionais por especialista
NUM_SAMPLES=30

echo "=============================================="
echo "Neural Hive - Geração de Samples Adicionais"
echo "=============================================="
echo ""
echo "Configuração:"
echo "  Provider: $LLM_PROVIDER"
echo "  Model: $LLM_MODEL"
echo "  Samples adicionais: $NUM_SAMPLES por especialista"
echo ""

# Status atual
echo "Status atual dos datasets:"
for f in data/specialist_*_base.parquet; do
    if [ -f "$f" ]; then
        count=$(python3 -c "import pandas as pd; df=pd.read_parquet('$f'); print(df.shape[0])" 2>/dev/null || echo "0")
        echo "  $(basename $f): $count samples"
    fi
done
echo ""

# Especialistas que precisam de mais dados (behavior, evolution, architecture)
# Ajuste esta lista conforme necessário
SPECIALISTS=("behavior" "evolution" "technical")

for specialist in "${SPECIALISTS[@]}"; do
    existing_file="data/specialist_${specialist}_base.parquet"
    temp_file="data/specialist_${specialist}_new.parquet"

    echo ""
    echo ">>> Gerando $NUM_SAMPLES samples adicionais para: $specialist"

    # Gerar novos samples em arquivo temporário
    python3 generate_training_datasets.py \
        --specialist-type "$specialist" \
        --num-samples "$NUM_SAMPLES" \
        --output-path "$temp_file" \
        --llm-provider deepseek \
        --llm-model deepseek-chat \
        --min-quality-score 0.5

    if [ $? -eq 0 ] && [ -f "$temp_file" ]; then
        # Combinar datasets existente + novo
        python3 -c "
import pandas as pd
import os

existing_file = '$existing_file'
temp_file = '$temp_file'

# Carregar datasets
if os.path.exists(existing_file):
    df_existing = pd.read_parquet(existing_file)
    print(f'  Existente: {len(df_existing)} samples')
else:
    df_existing = pd.DataFrame()
    print('  Existente: 0 samples')

df_new = pd.read_parquet(temp_file)
print(f'  Novos: {len(df_new)} samples')

# Combinar
df_combined = pd.concat([df_existing, df_new], ignore_index=True)
print(f'  Total combinado: {len(df_combined)} samples')

# Salvar
df_combined.to_parquet(existing_file, index=False)
print(f'  Salvo em: {existing_file}')

# Remover arquivo temporário
os.remove(temp_file)
"
        echo "✓ Dataset $specialist atualizado com sucesso!"
    else
        echo "✗ Erro ao gerar samples para $specialist"
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
        # Mostrar distribuição de labels
        labels=$(python3 -c "
import pandas as pd
df = pd.read_parquet('$f')
if 'label' in df.columns:
    counts = df['label'].value_counts().to_dict()
    label_names = {0: 'approve', 1: 'reject', 2: 'review', 3: 'conditional'}
    parts = [f\"{label_names.get(k, k)}:{v}\" for k, v in sorted(counts.items())]
    print(' | ' + ', '.join(parts))
" 2>/dev/null || echo "")
        echo "  $(basename $f): $count samples$labels"
    fi
done
echo "=============================================="
