#!/bin/bash
# generate_dataset.sh - Comando para gerar datasets de treinamento
#
# Uso: ml.sh generate-dataset [OPCOES]
#
# Exemplos:
#   ml.sh generate-dataset --specialist technical --num-samples 1000
#   ml.sh generate-dataset --all --llm-provider openai

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ml_common.sh"
source "${SCRIPT_DIR}/../lib/dataset_utils.sh"

# Opcoes padrao
SPECIALIST=""
ALL_SPECIALISTS=false
NUM_SAMPLES="${NUM_SAMPLES:-1000}"
LLM_PROVIDER="${LLM_PROVIDER:-openai}"
LLM_MODEL="${LLM_MODEL:-gpt-4}"
MIN_QUALITY_SCORE="${MIN_QUALITY_SCORE:-0.6}"
OUTPUT_DIR="${DATASET_DIR:-/data/training}"
VALIDATE_SCHEMA=true

# Funcao de ajuda
show_help() {
    cat << EOF
generate-dataset - Gerar datasets de treinamento para specialists

Uso: ml.sh generate-dataset [OPCOES]

OPCOES:
    --specialist TYPE        Tipo do especialista (technical|business|behavior|evolution|architecture)
    --all                    Gerar datasets para todos os 5 especialistas
    --num-samples N          Numero de amostras por dataset (padrao: 1000)
    --llm-provider PROVIDER  Provider LLM: openai (padrao), anthropic, ollama, groq, deepseek
    --llm-model MODEL        Modelo LLM a usar (padrao: gpt-4)
    --min-quality-score N    Score minimo de qualidade (padrao: 0.6)
    --output-dir PATH        Diretorio de saida (padrao: /data/training)
    --skip-validation        Pular validacao de schema apos geracao
    -h, --help               Mostrar esta mensagem

EXEMPLOS:
    ml.sh generate-dataset --specialist technical
    ml.sh generate-dataset --all --num-samples 500
    ml.sh generate-dataset --specialist business --llm-provider anthropic --llm-model claude-3-opus
    ml.sh generate-dataset --all --llm-provider groq --llm-model llama-3.1-70b-versatile

VARIAVEIS DE AMBIENTE:
    LLM_PROVIDER       Provider LLM (openai, anthropic, ollama, groq, deepseek)
    LLM_MODEL          Modelo LLM a usar
    LLM_API_KEY        Chave de API do provider LLM
    NUM_SAMPLES        Numero de amostras
    MIN_QUALITY_SCORE  Score minimo de qualidade
    OUTPUT_DIR         Diretorio de saida

NOTA: A geracao usa LLM para criar exemplos sinteticos de alta qualidade.
      Certifique-se de ter a API key configurada para o provider escolhido.

EOF
    exit 0
}

# Parse argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --specialist)
            SPECIALIST="$2"
            shift 2
            ;;
        --all)
            ALL_SPECIALISTS=true
            shift
            ;;
        --num-samples)
            NUM_SAMPLES="$2"
            shift 2
            ;;
        --llm-provider)
            LLM_PROVIDER="$2"
            shift 2
            ;;
        --llm-model)
            LLM_MODEL="$2"
            shift 2
            ;;
        --min-quality-score)
            MIN_QUALITY_SCORE="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --skip-validation)
            VALIDATE_SCHEMA=false
            shift
            ;;
        -h|--help)
            show_help
            ;;
        *)
            log_error "Opcao desconhecida: $1"
            exit 1
            ;;
    esac
done

# Validar argumentos
if [[ -z "$SPECIALIST" ]] && [[ "$ALL_SPECIALISTS" == "false" ]]; then
    log_error "Especifique --specialist TYPE ou --all"
    exit 1
fi

if [[ -n "$SPECIALIST" ]]; then
    validate_specialist_type "$SPECIALIST" || exit 1
fi

validate_llm_provider "$LLM_PROVIDER" || exit 1

# Verificar Python
if ! command -v python3 &> /dev/null; then
    log_error "python3 nao encontrado"
    exit 1
fi

# Funcao para gerar dataset de um specialist
generate_for_specialist() {
    local specialist="$1"
    local output_file="$OUTPUT_DIR/specialist_${specialist}_base.parquet"
    local start_time
    start_time=$(date +%s)

    log_section "Gerando Dataset: $specialist"

    log_info "Configuracao:"
    log_info "  Provider: $LLM_PROVIDER"
    log_info "  Modelo: $LLM_MODEL"
    log_info "  Amostras: $NUM_SAMPLES"
    log_info "  Quality Score Minimo: $MIN_QUALITY_SCORE"
    log_info "  Output: $output_file"
    echo ""

    # Criar diretorio de saida
    mkdir -p "$OUTPUT_DIR"

    # Executar geracao
    cd "${SCRIPT_DIR}/../training"

    if python3 generate_training_datasets.py \
        --specialist-type "$specialist" \
        --num-samples "$NUM_SAMPLES" \
        --output-path "$output_file" \
        --llm-provider "$LLM_PROVIDER" \
        --llm-model "$LLM_MODEL" \
        --min-quality-score "$MIN_QUALITY_SCORE"; then

        local end_time duration
        end_time=$(date +%s)
        duration=$((end_time - start_time))

        log_success "Dataset gerado em $(format_duration $duration)"

        # Validar Parquet basico
        if python3 -c "import pandas as pd; df=pd.read_parquet('$output_file'); print(f'  Shape: {df.shape}')"; then
            log_success "Arquivo Parquet valido"
        else
            log_error "Arquivo Parquet invalido"
            return 1
        fi

        # Validar schema
        if [[ "$VALIDATE_SCHEMA" == "true" ]]; then
            log_info "Validando schema..."
            local validation
            validation=$(validate_dataset_schema "$output_file" 2>/dev/null || echo "ERROR")

            if [[ "$validation" == OK:* ]]; then
                local features samples
                features=$(echo "$validation" | cut -d: -f2)
                samples=$(echo "$validation" | cut -d: -f3)
                log_success "Schema valido: $features features, $samples amostras"
            else
                log_warning "Problema no schema: $validation"
            fi
        fi

        return 0
    else
        log_error "Falha ao gerar dataset para $specialist"
        return 1
    fi
}

# Main
main() {
    log_phase "Neural Hive - Dataset Generation Pipeline"

    log_info "Configuracao Global:"
    log_info "  LLM Provider: $LLM_PROVIDER"
    log_info "  LLM Model: $LLM_MODEL"
    log_info "  Samples per Specialist: $NUM_SAMPLES"
    log_info "  Output Directory: $OUTPUT_DIR"
    log_info "  Min Quality Score: $MIN_QUALITY_SCORE"
    echo ""

    local total_start errors=0
    total_start=$(date +%s)

    if [[ "$ALL_SPECIALISTS" == "true" ]]; then
        local specialists=("technical" "business" "behavior" "evolution" "architecture")

        for spec in "${specialists[@]}"; do
            if ! generate_for_specialist "$spec"; then
                ((errors++))
            fi

            # Aguardar entre specialists para evitar rate limit
            if [[ "$spec" != "architecture" ]]; then
                log_info "Aguardando 5 segundos para evitar rate limit..."
                sleep 5
            fi
        done

        local total_end total_duration
        total_end=$(date +%s)
        total_duration=$((total_end - total_start))

        echo ""
        if [[ $errors -eq 0 ]]; then
            log_success "Todos os 5 datasets gerados com sucesso em $(format_duration $total_duration)"
        else
            log_error "$errors dataset(s) falharam"
            exit 1
        fi
    else
        if ! generate_for_specialist "$SPECIALIST"; then
            exit 1
        fi
    fi

    echo ""
    log_info "Datasets gerados:"
    ls -lh "$OUTPUT_DIR"/specialist_*_base.parquet 2>/dev/null || log_warning "Nenhum dataset encontrado"

    echo ""
    log_info "Proximos passos:"
    log_info "  1. Treinar modelos: ml.sh train --all"
    log_info "  2. Validar modelos: ml.sh validate --all"
}

main
