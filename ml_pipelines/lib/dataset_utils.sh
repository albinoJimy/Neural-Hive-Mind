#!/bin/bash
# dataset_utils.sh - Utilitarios para validacao de datasets
#
# Este arquivo fornece funcoes para validar e gerenciar datasets
# de treinamento para os modelos de specialists.
#
# Uso: source "${SCRIPT_DIR}/lib/dataset_utils.sh"

set -euo pipefail

# ============================================================================
# Funcoes de Verificacao de Existencia
# ============================================================================

# Verifica se dataset Parquet existe
# Uso: validate_dataset_exists "technical"
validate_dataset_exists() {
    local specialist="$1"
    local dataset_dir="${DATASET_DIR:-/data/training}"

    local dataset_file="$dataset_dir/specialist_${specialist}_base.parquet"

    if [[ -f "$dataset_file" ]]; then
        echo "$dataset_file"
        return 0
    fi

    # Tentar diretorio alternativo do projeto
    local project_dir
    project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    local alt_file="$project_dir/ml_pipelines/training/data/specialist_${specialist}_base.parquet"

    if [[ -f "$alt_file" ]]; then
        echo "$alt_file"
        return 0
    fi

    return 1
}

# Lista todos os datasets disponiveis
# Uso: list_available_datasets
list_available_datasets() {
    local dataset_dir="${DATASET_DIR:-/data/training}"
    local specialists=("technical" "business" "behavior" "evolution" "architecture")
    local found=()

    for spec in "${specialists[@]}"; do
        local file
        if file=$(validate_dataset_exists "$spec" 2>/dev/null); then
            found+=("$spec:$file")
        fi
    done

    if [[ ${#found[@]} -eq 0 ]]; then
        echo "NONE"
        return 1
    fi

    printf '%s\n' "${found[@]}"
}

# Conta amostras em dataset
# Uso: count_dataset_samples "/path/to/dataset.parquet"
count_dataset_samples() {
    local dataset_file="$1"

    if [[ ! -f "$dataset_file" ]]; then
        echo "0"
        return 1
    fi

    # Usar Python para contar linhas
    local count
    count=$(python3 -c "import pandas as pd; print(len(pd.read_parquet('$dataset_file')))" 2>/dev/null || echo "0")

    echo "$count"
}

# ============================================================================
# Funcoes de Validacao de Schema
# ============================================================================

# Valida schema de dataset contra feature_definitions.py
# Uso: validate_dataset_schema "/path/to/dataset.parquet"
validate_dataset_schema() {
    local dataset_file="$1"
    local project_dir
    project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

    if [[ ! -f "$dataset_file" ]]; then
        echo "ERROR: Dataset nao encontrado: $dataset_file"
        return 1
    fi

    # Validar schema usando Python
    local result
    result=$(python3 -c "
import pandas as pd
import sys
sys.path.insert(0, '$project_dir/ml_pipelines')

try:
    from feature_store.feature_definitions import get_feature_names
    expected_features = set(get_feature_names() + ['label'])
except ImportError:
    # Fallback se feature_definitions nao disponivel
    expected_features = None

df = pd.read_parquet('$dataset_file')
actual_columns = set(df.columns)

if expected_features is None:
    # Verificar apenas colunas basicas
    required = {'label'}
    if not required.issubset(actual_columns):
        print(f'MISSING_LABEL')
        sys.exit(1)
    print(f'OK:{len(df.columns)-1}:{len(df)}')
    sys.exit(0)

if expected_features != actual_columns:
    missing = expected_features - actual_columns
    extra = actual_columns - expected_features
    errors = []
    if missing:
        errors.append(f'missing={list(missing)[:5]}')
    if extra:
        errors.append(f'extra={list(extra)[:5]}')
    print('SCHEMA_MISMATCH:' + ','.join(errors))
    sys.exit(1)
else:
    print(f'OK:{len(df.columns)-1}:{len(df)}')
" 2>&1)

    local exit_code=$?
    echo "$result"
    return $exit_code
}

# Valida todos os datasets de uma vez
# Uso: validate_all_datasets
validate_all_datasets() {
    local specialists=("technical" "business" "behavior" "evolution" "architecture")
    local valid=0
    local invalid=0
    local missing=0

    for spec in "${specialists[@]}"; do
        local file
        if file=$(validate_dataset_exists "$spec" 2>/dev/null); then
            local validation
            validation=$(validate_dataset_schema "$file" 2>/dev/null)
            if [[ "$validation" == OK:* ]]; then
                local features samples
                features=$(echo "$validation" | cut -d: -f2)
                samples=$(echo "$validation" | cut -d: -f3)
                echo "OK:$spec:$features features:$samples samples"
                ((valid++))
            else
                echo "INVALID:$spec:$validation"
                ((invalid++))
            fi
        else
            echo "MISSING:$spec"
            ((missing++))
        fi
    done

    echo ""
    echo "SUMMARY:valid=$valid,invalid=$invalid,missing=$missing"

    if [[ $invalid -gt 0 ]]; then
        return 1
    fi
    return 0
}

# ============================================================================
# Funcoes de Informacao de Dataset
# ============================================================================

# Obtem informacoes detalhadas de um dataset
# Uso: get_dataset_info "/path/to/dataset.parquet"
get_dataset_info() {
    local dataset_file="$1"

    if [[ ! -f "$dataset_file" ]]; then
        echo "{\"error\": \"Dataset nao encontrado\"}"
        return 1
    fi

    # Obter informacoes via Python
    python3 -c "
import pandas as pd
import json
import os
from datetime import datetime

df = pd.read_parquet('$dataset_file')
stat = os.stat('$dataset_file')

info = {
    'file': '$dataset_file',
    'size_mb': round(stat.st_size / (1024*1024), 2),
    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
    'samples': len(df),
    'features': len(df.columns) - 1,  # Excluir label
    'columns': list(df.columns)[:10],  # Primeiras 10 colunas
    'label_distribution': df['label'].value_counts().to_dict() if 'label' in df.columns else {}
}

print(json.dumps(info, indent=2))
" 2>/dev/null
}

# ============================================================================
# Funcoes de Limpeza e Manutencao
# ============================================================================

# Lista datasets antigos (mais de N dias)
# Uso: list_old_datasets 30
list_old_datasets() {
    local days="${1:-30}"
    local dataset_dir="${DATASET_DIR:-/data/training}"

    find "$dataset_dir" -name "specialist_*_base.parquet" -mtime "+$days" 2>/dev/null || true
}

# Verifica integridade de dataset (pode ser lido sem erros)
# Uso: check_dataset_integrity "/path/to/dataset.parquet"
check_dataset_integrity() {
    local dataset_file="$1"

    if [[ ! -f "$dataset_file" ]]; then
        echo "ERROR:FILE_NOT_FOUND"
        return 1
    fi

    # Tentar ler o arquivo Parquet
    local result
    result=$(python3 -c "
import pandas as pd
import sys

try:
    df = pd.read_parquet('$dataset_file')
    # Verificar se tem dados
    if len(df) == 0:
        print('ERROR:EMPTY_DATASET')
        sys.exit(1)
    # Verificar se tem label
    if 'label' not in df.columns:
        print('ERROR:MISSING_LABEL')
        sys.exit(1)
    # Verificar se tem features
    if len(df.columns) < 2:
        print('ERROR:NO_FEATURES')
        sys.exit(1)
    print(f'OK:{len(df)}')
except Exception as e:
    print(f'ERROR:{type(e).__name__}')
    sys.exit(1)
" 2>&1)

    echo "$result"
    if [[ "$result" == OK:* ]]; then
        return 0
    fi
    return 1
}

# ============================================================================
# Funcoes de Estatisticas
# ============================================================================

# Obtem estatisticas resumidas de todos os datasets
# Uso: get_datasets_summary
get_datasets_summary() {
    local specialists=("technical" "business" "behavior" "evolution" "architecture")
    local total_samples=0
    local total_size=0

    echo "{"
    echo "  \"datasets\": {"

    local first=true
    for spec in "${specialists[@]}"; do
        local file
        if file=$(validate_dataset_exists "$spec" 2>/dev/null); then
            if [[ "$first" != "true" ]]; then
                echo ","
            fi
            first=false

            local samples size_kb
            samples=$(count_dataset_samples "$file")
            size_kb=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo "0")
            size_kb=$((size_kb / 1024))

            total_samples=$((total_samples + samples))
            total_size=$((total_size + size_kb))

            printf "    \"%s\": {\"samples\": %s, \"size_kb\": %s, \"file\": \"%s\"}" "$spec" "$samples" "$size_kb" "$file"
        fi
    done

    echo ""
    echo "  },"
    echo "  \"total_samples\": $total_samples,"
    echo "  \"total_size_kb\": $total_size"
    echo "}"
}

# Exportar funcoes
export -f validate_dataset_exists list_available_datasets count_dataset_samples
export -f validate_dataset_schema validate_all_datasets
export -f get_dataset_info
export -f list_old_datasets check_dataset_integrity
export -f get_datasets_summary
