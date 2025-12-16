#!/bin/bash
# mlflow_utils.sh - Utilitarios para operacoes MLflow
#
# Este arquivo fornece funcoes para interagir com a API do MLflow,
# incluindo consultas de modelos, promocao e rollback.
#
# Uso: source "${SCRIPT_DIR}/lib/mlflow_utils.sh"

set -euo pipefail

# ============================================================================
# Funcoes de Query de Modelos
# ============================================================================

# Obtem informacoes de um modelo registrado
# Uso: mlflow_get_model_info "technical-evaluator"
mlflow_get_model_info() {
    local model_name="$1"
    local mlflow_uri="${MLFLOW_URI:-http://mlflow.mlflow:5000}"

    local response
    response=$(curl -sf "$mlflow_uri/api/2.0/mlflow/registered-models/get?name=$model_name" 2>/dev/null || echo "{}")

    # Verificar se modelo existe
    if ! echo "$response" | jq -e '.registered_model' > /dev/null 2>&1; then
        return 1
    fi

    echo "$response"
}

# Obtem todas as versoes de um modelo
# Uso: mlflow_get_model_versions "technical-evaluator"
mlflow_get_model_versions() {
    local model_name="$1"
    local mlflow_uri="${MLFLOW_URI:-http://mlflow.mlflow:5000}"

    local response
    response=$(curl -sf "$mlflow_uri/api/2.0/mlflow/model-versions/search?filter=name='$model_name'" 2>/dev/null || echo "{}")

    echo "$response"
}

# Obtem versao em Production de um modelo
# Uso: mlflow_get_production_version "technical-evaluator"
mlflow_get_production_version() {
    local model_name="$1"

    local versions
    versions=$(mlflow_get_model_versions "$model_name")

    local prod_version
    prod_version=$(echo "$versions" | jq -r '.model_versions[] | select(.current_stage=="Production") | .version' 2>/dev/null | head -n 1)

    if [[ -z "$prod_version" ]] || [[ "$prod_version" == "null" ]]; then
        return 1
    fi

    echo "$prod_version"
}

# Obtem versao em Staging de um modelo
# Uso: mlflow_get_staging_version "technical-evaluator"
mlflow_get_staging_version() {
    local model_name="$1"

    local versions
    versions=$(mlflow_get_model_versions "$model_name")

    local staging_version
    staging_version=$(echo "$versions" | jq -r '.model_versions[] | select(.current_stage=="Staging") | .version' 2>/dev/null | head -n 1)

    if [[ -z "$staging_version" ]] || [[ "$staging_version" == "null" ]]; then
        return 1
    fi

    echo "$staging_version"
}

# Obtem versao mais recente de um modelo
# Uso: mlflow_get_latest_version "technical-evaluator"
mlflow_get_latest_version() {
    local model_name="$1"

    local versions
    versions=$(mlflow_get_model_versions "$model_name")

    local latest_version
    latest_version=$(echo "$versions" | jq -r '.model_versions | sort_by(.version | tonumber) | reverse | .[0].version' 2>/dev/null)

    if [[ -z "$latest_version" ]] || [[ "$latest_version" == "null" ]]; then
        return 1
    fi

    echo "$latest_version"
}

# ============================================================================
# Funcoes de Metricas
# ============================================================================

# Obtem metricas de um run MLflow
# Uso: mlflow_get_run_metrics "run_id_here"
mlflow_get_run_metrics() {
    local run_id="$1"
    local mlflow_uri="${MLFLOW_URI:-http://mlflow.mlflow:5000}"

    local response
    response=$(curl -sf "$mlflow_uri/api/2.0/mlflow/runs/get?run_id=$run_id" 2>/dev/null || echo "{}")

    # Extrair metricas principais
    local precision recall f1 accuracy
    precision=$(echo "$response" | jq -r '.run.data.metrics[] | select(.key=="precision") | .value' 2>/dev/null || echo "N/A")
    recall=$(echo "$response" | jq -r '.run.data.metrics[] | select(.key=="recall") | .value' 2>/dev/null || echo "N/A")
    f1=$(echo "$response" | jq -r '.run.data.metrics[] | select(.key=="f1") | .value' 2>/dev/null || echo "N/A")
    accuracy=$(echo "$response" | jq -r '.run.data.metrics[] | select(.key=="accuracy") | .value' 2>/dev/null || echo "N/A")

    echo "{\"precision\": \"$precision\", \"recall\": \"$recall\", \"f1\": \"$f1\", \"accuracy\": \"$accuracy\"}"
}

# Obtem run_id de uma versao de modelo
# Uso: mlflow_get_version_run_id "technical-evaluator" "3"
mlflow_get_version_run_id() {
    local model_name="$1"
    local version="$2"

    local versions
    versions=$(mlflow_get_model_versions "$model_name")

    local run_id
    run_id=$(echo "$versions" | jq -r ".model_versions[] | select(.version==\"$version\") | .run_id" 2>/dev/null)

    if [[ -z "$run_id" ]] || [[ "$run_id" == "null" ]]; then
        return 1
    fi

    echo "$run_id"
}

# Obtem metricas de uma versao especifica de modelo
# Uso: mlflow_get_version_metrics "technical-evaluator" "3"
mlflow_get_version_metrics() {
    local model_name="$1"
    local version="$2"

    local run_id
    run_id=$(mlflow_get_version_run_id "$model_name" "$version") || return 1

    mlflow_get_run_metrics "$run_id"
}

# ============================================================================
# Funcoes de Promocao/Transicao de Stage
# ============================================================================

# Promove modelo para um stage
# Uso: mlflow_promote_model "technical-evaluator" "3" "Production"
mlflow_promote_model() {
    local model_name="$1"
    local version="$2"
    local target_stage="$3"
    local archive_existing="${4:-true}"
    local mlflow_uri="${MLFLOW_URI:-http://mlflow.mlflow:5000}"

    local response
    response=$(curl -sf -X POST "$mlflow_uri/api/2.0/mlflow/model-versions/transition-stage" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"$model_name\",
            \"version\": \"$version\",
            \"stage\": \"$target_stage\",
            \"archive_existing_versions\": $archive_existing
        }" 2>/dev/null || echo "{}")

    if ! echo "$response" | jq -e '.model_version' > /dev/null 2>&1; then
        return 1
    fi

    echo "$response"
}

# Arquiva uma versao de modelo
# Uso: mlflow_archive_model "technical-evaluator" "2"
mlflow_archive_model() {
    local model_name="$1"
    local version="$2"

    mlflow_promote_model "$model_name" "$version" "Archived" "false"
}

# ============================================================================
# Funcoes de Tags
# ============================================================================

# Adiciona tag a uma versao de modelo
# Uso: mlflow_add_tag "technical-evaluator" "3" "promoted_by" "ml.sh"
mlflow_add_tag() {
    local model_name="$1"
    local version="$2"
    local key="$3"
    local value="$4"
    local mlflow_uri="${MLFLOW_URI:-http://mlflow.mlflow:5000}"

    curl -sf -X POST "$mlflow_uri/api/2.0/mlflow/model-versions/set-tag" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"$model_name\",
            \"version\": \"$version\",
            \"key\": \"$key\",
            \"value\": \"$value\"
        }" > /dev/null 2>&1
}

# Adiciona multiplas tags de auditoria
# Uso: mlflow_add_audit_tags "technical-evaluator" "3" "promoted" "Metricas excelentes"
mlflow_add_audit_tags() {
    local model_name="$1"
    local version="$2"
    local action="$3"
    local reason="${4:-}"

    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    mlflow_add_tag "$model_name" "$version" "ml_cli_action" "$action"
    mlflow_add_tag "$model_name" "$version" "ml_cli_timestamp" "$timestamp"
    mlflow_add_tag "$model_name" "$version" "ml_cli_user" "${USER:-unknown}"

    if [[ -n "$reason" ]]; then
        mlflow_add_tag "$model_name" "$version" "ml_cli_reason" "$reason"
    fi
}

# ============================================================================
# Funcoes de Validacao de Thresholds
# ============================================================================

# Verifica se metricas atingem thresholds de promocao
# Uso: mlflow_check_promotion_thresholds "technical-evaluator" "3"
mlflow_check_promotion_thresholds() {
    local model_name="$1"
    local version="$2"

    local metrics
    metrics=$(mlflow_get_version_metrics "$model_name" "$version") || return 1

    local precision recall f1 accuracy
    precision=$(echo "$metrics" | jq -r '.precision' 2>/dev/null)
    recall=$(echo "$metrics" | jq -r '.recall' 2>/dev/null)
    f1=$(echo "$metrics" | jq -r '.f1' 2>/dev/null)
    accuracy=$(echo "$metrics" | jq -r '.accuracy' 2>/dev/null)

    # Verificar thresholds
    local threshold_precision="${PROMOTION_THRESHOLD_PRECISION:-0.75}"
    local threshold_recall="${PROMOTION_THRESHOLD_RECALL:-0.70}"
    local threshold_f1="${PROMOTION_THRESHOLD_F1:-0.72}"

    local passed=true
    local errors=""

    if [[ "$precision" != "N/A" ]] && [[ "$precision" != "null" ]]; then
        if (( $(echo "$precision < $threshold_precision" | bc -l 2>/dev/null || echo "1") )); then
            passed=false
            errors="$errors precision=$precision<$threshold_precision"
        fi
    fi

    if [[ "$recall" != "N/A" ]] && [[ "$recall" != "null" ]]; then
        if (( $(echo "$recall < $threshold_recall" | bc -l 2>/dev/null || echo "1") )); then
            passed=false
            errors="$errors recall=$recall<$threshold_recall"
        fi
    fi

    if [[ "$f1" != "N/A" ]] && [[ "$f1" != "null" ]]; then
        if (( $(echo "$f1 < $threshold_f1" | bc -l 2>/dev/null || echo "1") )); then
            passed=false
            errors="$errors f1=$f1<$threshold_f1"
        fi
    fi

    if [[ "$passed" == "false" ]]; then
        echo "FAILED:$errors"
        return 1
    fi

    echo "PASSED: precision=$precision recall=$recall f1=$f1 accuracy=$accuracy"
    return 0
}

# ============================================================================
# Funcoes de Comparacao
# ============================================================================

# Compara metricas entre duas versoes
# Uso: mlflow_compare_versions "technical-evaluator" "2" "3"
mlflow_compare_versions() {
    local model_name="$1"
    local version_a="$2"
    local version_b="$3"

    local metrics_a metrics_b
    metrics_a=$(mlflow_get_version_metrics "$model_name" "$version_a" 2>/dev/null || echo '{"f1":"N/A"}')
    metrics_b=$(mlflow_get_version_metrics "$model_name" "$version_b" 2>/dev/null || echo '{"f1":"N/A"}')

    local f1_a f1_b
    f1_a=$(echo "$metrics_a" | jq -r '.f1' 2>/dev/null || echo "N/A")
    f1_b=$(echo "$metrics_b" | jq -r '.f1' 2>/dev/null || echo "N/A")

    echo "{\"version_a\": \"$version_a\", \"version_b\": \"$version_b\", \"f1_a\": \"$f1_a\", \"f1_b\": \"$f1_b\"}"

    # Calcular delta se ambos sao numericos
    if [[ "$f1_a" != "N/A" ]] && [[ "$f1_b" != "N/A" ]] && \
       [[ "$f1_a" != "null" ]] && [[ "$f1_b" != "null" ]]; then
        if command -v bc &> /dev/null && [[ "$f1_a" != "0" ]]; then
            local delta
            delta=$(echo "scale=4; ($f1_b - $f1_a) / $f1_a * 100" | bc -l 2>/dev/null || echo "0")
            echo "Delta F1: ${delta}%"
        fi
    fi
}

# Exportar funcoes
export -f mlflow_get_model_info mlflow_get_model_versions
export -f mlflow_get_production_version mlflow_get_staging_version mlflow_get_latest_version
export -f mlflow_get_run_metrics mlflow_get_version_run_id mlflow_get_version_metrics
export -f mlflow_promote_model mlflow_archive_model
export -f mlflow_add_tag mlflow_add_audit_tags
export -f mlflow_check_promotion_thresholds mlflow_compare_versions
