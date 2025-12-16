#!/bin/bash
# train.sh - Comando para treinar modelos de specialists
#
# Uso: ml.sh train [OPCOES]
#
# Exemplos:
#   ml.sh train --specialist technical
#   ml.sh train --all
#   ml.sh train --specialist business --model-type gradient_boosting --hyperparameter-tuning

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ml_common.sh"
source "${SCRIPT_DIR}/../lib/mlflow_utils.sh"
source "${SCRIPT_DIR}/../lib/dataset_utils.sh"

# Opcoes padrao
SPECIALIST=""
ALL_SPECIALISTS=false
MODEL_TYPE="random_forest"
HYPERPARAMETER_TUNING=false
AUTO_PROMOTE=false
PROMOTE_IF_BETTER="${PROMOTE_IF_BETTER:-true}"
DRY_RUN=false

# Funcao de ajuda
show_help() {
    cat << EOF
train - Treinar modelos de specialists

Uso: ml.sh train [OPCOES]

OPCOES:
    --specialist TYPE        Tipo do especialista (technical|business|behavior|evolution|architecture)
    --all                    Treinar todos os 5 especialistas
    --model-type TYPE        Tipo de modelo: random_forest (padrao), gradient_boosting, neural_network
    --hyperparameter-tuning  Habilitar GridSearchCV para otimizacao de hiperparametros
    --auto-promote           Promover automaticamente se metricas atingirem thresholds
    --dry-run                Simular treinamento sem executar
    -h, --help               Mostrar esta mensagem

EXEMPLOS:
    ml.sh train --specialist technical
    ml.sh train --all --hyperparameter-tuning
    ml.sh train --specialist business --model-type gradient_boosting --auto-promote

VARIAVEIS DE AMBIENTE:
    MLFLOW_TRACKING_URI      URI do MLflow (padrao: http://mlflow.mlflow:5000)
    MONGODB_URI              URI do MongoDB para incluir feedbacks
    DATASET_DIR              Diretorio de datasets (padrao: /data/training)
    ALLOW_SYNTHETIC_FALLBACK Se true, usa dados sinteticos quando dataset nao disponivel

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
        --model-type)
            MODEL_TYPE="$2"
            shift 2
            ;;
        --hyperparameter-tuning)
            HYPERPARAMETER_TUNING=true
            shift
            ;;
        --auto-promote)
            AUTO_PROMOTE=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            show_help
            ;;
        *)
            log_error "Opcao desconhecida: $1"
            echo "Use 'ml.sh train --help' para ver opcoes disponiveis."
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

validate_model_type "$MODEL_TYPE" || exit 1

# Funcao principal de treinamento
train_specialist() {
    local specialist="$1"
    local start_time
    start_time=$(date +%s)

    log_section "Treinando Specialist: $specialist"

    # Verificar dataset
    local dataset_file
    if ! dataset_file=$(validate_dataset_exists "$specialist" 2>/dev/null); then
        log_warning "Dataset nao encontrado para $specialist"
        if [[ "${ALLOW_SYNTHETIC_FALLBACK:-true}" == "true" ]]; then
            log_info "Usando fallback sintetico..."
        else
            log_error "ALLOW_SYNTHETIC_FALLBACK=false e dataset nao existe"
            return 1
        fi
    else
        log_info "Dataset: $dataset_file"
        local samples
        samples=$(count_dataset_samples "$dataset_file")
        log_info "Amostras: $samples"
    fi

    # Construir comando
    local cmd="python3 ${SCRIPT_DIR}/../training/train_specialist_model.py"
    cmd="$cmd --specialist-type $specialist"
    cmd="$cmd --model-type $MODEL_TYPE"

    if [[ "$HYPERPARAMETER_TUNING" == "true" ]]; then
        cmd="$cmd --hyperparameter-tuning true"
    else
        cmd="$cmd --hyperparameter-tuning false"
    fi

    cmd="$cmd --promote-if-better $PROMOTE_IF_BETTER"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_warning "[DRY-RUN] Comando que seria executado:"
        log_info "$cmd"
        return 0
    fi

    # Executar treinamento
    log_info "Executando: $cmd"
    cd "${SCRIPT_DIR}/../training"

    if eval "$cmd"; then
        local end_time duration
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        log_success "Treinamento de $specialist concluido em $(format_duration $duration)"

        # Auto-promocao se solicitada
        if [[ "$AUTO_PROMOTE" == "true" ]]; then
            local model_name="${specialist}-evaluator"
            local latest_version
            if latest_version=$(mlflow_get_latest_version "$model_name" 2>/dev/null); then
                log_info "Verificando thresholds para promocao automatica..."
                local check_result
                if check_result=$(mlflow_check_promotion_thresholds "$model_name" "$latest_version" 2>/dev/null); then
                    if [[ "$check_result" == PASSED:* ]]; then
                        log_info "Metricas atingiram thresholds, promovendo para Production..."
                        if mlflow_promote_model "$model_name" "$latest_version" "Production" "true" > /dev/null 2>&1; then
                            mlflow_add_audit_tags "$model_name" "$latest_version" "auto-promoted" "Thresholds atingidos via ml.sh train --auto-promote"
                            log_success "Modelo promovido para Production: $model_name v$latest_version"
                        fi
                    else
                        log_warning "Metricas nao atingiram thresholds: $check_result"
                    fi
                fi
            fi
        fi

        return 0
    else
        log_error "Treinamento de $specialist falhou"
        return 1
    fi
}

# Main
main() {
    log_phase "Neural Hive - Model Training Pipeline"

    # Pre-flight checks
    if [[ "$ALL_SPECIALISTS" == "true" ]]; then
        preflight_checks_training "all" || exit 1
    else
        preflight_checks_training "$SPECIALIST" || exit 1
    fi

    log_info "Configuracao:"
    log_info "  Model Type: $MODEL_TYPE"
    log_info "  Hyperparameter Tuning: $HYPERPARAMETER_TUNING"
    log_info "  Auto-Promote: $AUTO_PROMOTE"
    log_info "  Dry-Run: $DRY_RUN"
    echo ""

    local total_start errors=0
    total_start=$(date +%s)

    if [[ "$ALL_SPECIALISTS" == "true" ]]; then
        local specialists=("technical" "business" "behavior" "evolution" "architecture")

        for spec in "${specialists[@]}"; do
            if ! train_specialist "$spec"; then
                ((errors++))
            fi

            # Aguardar entre specialists para evitar contencao
            if [[ "$spec" != "architecture" ]] && [[ "$DRY_RUN" != "true" ]]; then
                log_info "Aguardando 2 segundos..."
                sleep 2
            fi
        done

        local total_end total_duration
        total_end=$(date +%s)
        total_duration=$((total_end - total_start))

        echo ""
        if [[ $errors -eq 0 ]]; then
            log_success "Todos os 5 modelos treinados com sucesso em $(format_duration $total_duration)"
        else
            log_error "$errors modelo(s) falharam"
            exit 1
        fi
    else
        if ! train_specialist "$SPECIALIST"; then
            exit 1
        fi
    fi

    echo ""
    log_info "Proximos passos:"
    log_info "  1. Validar modelos: ml.sh validate --all"
    log_info "  2. Verificar status: ml.sh status --all --verbose"
    log_info "  3. Promover modelos: ml.sh promote --model TYPE-evaluator --version N"
}

main
