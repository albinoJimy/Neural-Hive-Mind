#!/bin/bash
# promote.sh - Comando para promover modelos entre stages
#
# Uso: ml.sh promote [OPCOES]
#
# Exemplos:
#   ml.sh promote --model technical-evaluator --version 3
#   ml.sh promote --model business-evaluator --version 2 --target-stage Production

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ml_common.sh"
source "${SCRIPT_DIR}/../lib/mlflow_utils.sh"

# Opcoes padrao
MODEL_NAME=""
MODEL_VERSION=""
TARGET_STAGE="Production"
ARCHIVE_EXISTING=true
SKIP_VALIDATION=false
REASON=""
DRY_RUN=false

# Funcao de ajuda
show_help() {
    cat << EOF
promote - Promover modelo entre stages no MLflow

Uso: ml.sh promote [OPCOES]

OPCOES OBRIGATORIAS:
    --model NAME          Nome do modelo (ex: technical-evaluator, business-evaluator)
    --version N           Versao do modelo a promover

OPCOES OPCIONAIS:
    --target-stage STAGE  Stage de destino: Production (padrao), Staging, Archived
    --stage STAGE         Alias para --target-stage
    --no-archive-existing Nao arquivar versao existente no stage de destino
    --skip-validation     Pular validacao de thresholds antes de promover
    --reason TEXT         Motivo da promocao (para auditoria)
    --dry-run             Simular promocao sem executar
    -h, --help            Mostrar esta mensagem

EXEMPLOS:
    ml.sh promote --model technical-evaluator --version 3
    ml.sh promote --model business-evaluator --version 2 --target-stage Staging
    ml.sh promote --model evolution-evaluator --version 4 --reason "Metricas melhoradas"
    ml.sh promote --model behavior-evaluator --version 1 --skip-validation

THRESHOLDS DE PROMOCAO (padrao):
    Precision >= 0.75
    Recall    >= 0.70
    F1 Score  >= 0.72

Os thresholds podem ser alterados via variaveis de ambiente:
    PROMOTION_THRESHOLD_PRECISION
    PROMOTION_THRESHOLD_RECALL
    PROMOTION_THRESHOLD_F1

EOF
    exit 0
}

# Parse argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --model)
            MODEL_NAME="$2"
            shift 2
            ;;
        --version)
            MODEL_VERSION="$2"
            shift 2
            ;;
        --target-stage|--stage)
            TARGET_STAGE="$2"
            shift 2
            ;;
        --no-archive-existing)
            ARCHIVE_EXISTING=false
            shift
            ;;
        --skip-validation)
            SKIP_VALIDATION=true
            shift
            ;;
        --reason)
            REASON="$2"
            shift 2
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
            exit 1
            ;;
    esac
done

# Validar argumentos obrigatorios
if [[ -z "$MODEL_NAME" ]]; then
    log_error "--model e obrigatorio"
    echo "Use 'ml.sh promote --help' para ver opcoes."
    exit 1
fi

if [[ -z "$MODEL_VERSION" ]]; then
    log_error "--version e obrigatorio"
    exit 1
fi

# Validar target stage
valid_stages=("Production" "Staging" "Archived" "None")
if [[ ! " ${valid_stages[*]} " =~ " ${TARGET_STAGE} " ]]; then
    log_error "Stage invalido: $TARGET_STAGE"
    log_info "Stages validos: ${valid_stages[*]}"
    exit 1
fi

# Main
main() {
    log_phase "Neural Hive - Model Promotion"

    # Verificar MLflow
    if ! check_mlflow_connection; then
        exit 1
    fi

    # Verificar se modelo existe
    log_info "Verificando modelo: $MODEL_NAME v$MODEL_VERSION"

    if ! mlflow_get_model_info "$MODEL_NAME" > /dev/null 2>&1; then
        log_error "Modelo nao encontrado: $MODEL_NAME"
        exit 1
    fi

    # Verificar se versao existe
    local versions
    versions=$(mlflow_get_model_versions "$MODEL_NAME")
    local version_exists
    version_exists=$(echo "$versions" | jq -r ".model_versions[] | select(.version==\"$MODEL_VERSION\") | .version" 2>/dev/null)

    if [[ -z "$version_exists" ]] || [[ "$version_exists" == "null" ]]; then
        log_error "Versao nao encontrada: v$MODEL_VERSION"
        log_info "Versoes disponiveis:"
        echo "$versions" | jq -r '.model_versions[] | "  v\(.version) (\(.current_stage))"' 2>/dev/null
        exit 1
    fi

    # Obter stage atual
    local current_stage
    current_stage=$(echo "$versions" | jq -r ".model_versions[] | select(.version==\"$MODEL_VERSION\") | .current_stage" 2>/dev/null)
    log_info "Stage atual: $current_stage"

    # Obter metricas
    local metrics
    metrics=$(mlflow_get_version_metrics "$MODEL_NAME" "$MODEL_VERSION" 2>/dev/null || echo "{}")

    local precision recall f1 accuracy
    precision=$(echo "$metrics" | jq -r '.precision' 2>/dev/null || echo "N/A")
    recall=$(echo "$metrics" | jq -r '.recall' 2>/dev/null || echo "N/A")
    f1=$(echo "$metrics" | jq -r '.f1' 2>/dev/null || echo "N/A")
    accuracy=$(echo "$metrics" | jq -r '.accuracy' 2>/dev/null || echo "N/A")

    log_info "Metricas: P=$precision R=$recall F1=$f1 Acc=$accuracy"

    # Validar thresholds (se nao pular)
    if [[ "$SKIP_VALIDATION" != "true" ]] && [[ "$TARGET_STAGE" == "Production" ]]; then
        log_info "Validando thresholds de promocao..."

        local check_result
        if ! check_result=$(mlflow_check_promotion_thresholds "$MODEL_NAME" "$MODEL_VERSION" 2>/dev/null); then
            log_error "Metricas nao atingem thresholds: $check_result"
            log_info "Use --skip-validation para ignorar esta verificacao"
            exit 1
        fi

        log_success "Thresholds validados"
    fi

    # Verificar versao atual em Production
    if [[ "$TARGET_STAGE" == "Production" ]]; then
        local current_prod
        if current_prod=$(mlflow_get_production_version "$MODEL_NAME" 2>/dev/null); then
            log_info "Versao atual em Production: v$current_prod"

            if [[ "$ARCHIVE_EXISTING" == "true" ]]; then
                log_info "Versao v$current_prod sera arquivada"
            fi
        fi
    fi

    echo ""

    # Dry run
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warning "[DRY-RUN] Promocao nao sera executada"
        log_info "Acoes que seriam executadas:"
        log_info "  1. Transicionar v$MODEL_VERSION para $TARGET_STAGE"
        if [[ "$ARCHIVE_EXISTING" == "true" ]] && [[ "$TARGET_STAGE" == "Production" ]]; then
            log_info "  2. Arquivar versao anterior"
        fi
        log_info "  3. Adicionar tags de auditoria"
        exit 0
    fi

    # Executar promocao
    log_info "Promovendo modelo..."

    local archive_flag="true"
    if [[ "$ARCHIVE_EXISTING" == "false" ]]; then
        archive_flag="false"
    fi

    if ! mlflow_promote_model "$MODEL_NAME" "$MODEL_VERSION" "$TARGET_STAGE" "$archive_flag" > /dev/null 2>&1; then
        log_error "Falha ao promover modelo"
        exit 1
    fi

    # Adicionar tags de auditoria
    local audit_reason="${REASON:-Promocao via ml.sh CLI}"
    mlflow_add_audit_tags "$MODEL_NAME" "$MODEL_VERSION" "promoted_to_$TARGET_STAGE" "$audit_reason"

    log_success "Modelo promovido com sucesso!"
    log_info "  Modelo:  $MODEL_NAME"
    log_info "  Versao:  v$MODEL_VERSION"
    log_info "  Stage:   $TARGET_STAGE"

    echo ""
    log_info "Proximos passos:"
    log_info "  1. Validar: ml.sh validate --all"
    log_info "  2. Reiniciar pods para carregar novo modelo:"

    # Extrair tipo de specialist do nome do modelo
    local specialist_type
    specialist_type=$(echo "$MODEL_NAME" | sed 's/-evaluator$//')
    log_info "     kubectl rollout restart deployment/specialist-$specialist_type -n ${K8S_NAMESPACE:-neural-hive}"
}

main
