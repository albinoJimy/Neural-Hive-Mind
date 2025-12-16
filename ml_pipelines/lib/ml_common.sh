#!/bin/bash
# ml_common.sh - Biblioteca compartilhada com funcoes comuns para operacoes ML
#
# Este arquivo fornece funcoes utilitarias para os comandos do CLI ml.sh,
# incluindo logging, validacoes e verificacao de conexoes.
#
# Uso: source "${SCRIPT_DIR}/lib/ml_common.sh"

set -euo pipefail

# Carregar biblioteca comum do projeto (se disponivel)
COMMON_LIB="${SCRIPT_DIR:-$(dirname "${BASH_SOURCE[0]}")}/../../scripts/lib/common.sh"
if [[ -f "$COMMON_LIB" ]]; then
    source "$COMMON_LIB"
else
    # Definir funcoes de logging se common.sh nao disponivel
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    PURPLE='\033[0;35m'
    CYAN='\033[0;36m'
    NC='\033[0m'

    log_timestamp() {
        date "+%Y-%m-%d %H:%M:%S"
    }

    log_info() {
        printf "%b[%s] [INFO] %s%b\n" "${BLUE}" "$(log_timestamp)" "$*" "${NC}" >&2
    }

    log_success() {
        printf "%b[%s] %s%b\n" "${GREEN}" "$(log_timestamp)" "$*" "${NC}" >&2
    }

    log_error() {
        printf "%b[%s] %s%b\n" "${RED}" "$(log_timestamp)" "$*" "${NC}" >&2
    }

    log_warning() {
        printf "%b[%s] %s%b\n" "${YELLOW}" "$(log_timestamp)" "$*" "${NC}" >&2
    }

    log_debug() {
        if [[ "${DEBUG:-false}" == "true" ]]; then
            printf "%b[%s] [DEBUG] %s%b\n" "${PURPLE}" "$(log_timestamp)" "$*" "${NC}" >&2
        fi
    }

    log_section() {
        printf "\n%b========== %s ==========%b\n" "${CYAN}" "$*" "${NC}" >&2
    }

    log_phase() {
        printf "\n%b========== %s ==========%b\n" "${BLUE}" "$*" "${NC}" >&2
    }
fi

# ============================================================================
# Configuracoes Padrao
# ============================================================================

export MLFLOW_URI="${MLFLOW_URI:-http://mlflow.mlflow:5000}"
export MONGODB_URI="${MONGODB_URI:-mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin}"
export DATASET_DIR="${DATASET_DIR:-/data/training}"
export K8S_NAMESPACE="${K8S_NAMESPACE:-neural-hive}"

# Lista de especialistas validos
VALID_SPECIALISTS=("technical" "business" "behavior" "evolution" "architecture")

# Lista de tipos de modelo validos
VALID_MODEL_TYPES=("random_forest" "gradient_boosting" "neural_network")

# Lista de providers LLM validos
VALID_LLM_PROVIDERS=("openai" "anthropic" "ollama" "groq" "deepseek")

# Thresholds de metricas para promocao
PROMOTION_THRESHOLD_PRECISION="${PROMOTION_THRESHOLD_PRECISION:-0.75}"
PROMOTION_THRESHOLD_RECALL="${PROMOTION_THRESHOLD_RECALL:-0.70}"
PROMOTION_THRESHOLD_F1="${PROMOTION_THRESHOLD_F1:-0.72}"
PROMOTION_THRESHOLD_ACCURACY="${PROMOTION_THRESHOLD_ACCURACY:-0.70}"

# ============================================================================
# Funcoes de Validacao
# ============================================================================

# Valida se o tipo de especialista e valido
# Uso: validate_specialist_type "technical"
validate_specialist_type() {
    local specialist="${1:-}"

    if [[ -z "$specialist" ]]; then
        log_error "Tipo de especialista nao especificado"
        return 1
    fi

    if [[ ! " ${VALID_SPECIALISTS[*]} " =~ " ${specialist} " ]]; then
        log_error "Especialista invalido: $specialist"
        log_info "Especialistas validos: ${VALID_SPECIALISTS[*]}"
        return 1
    fi

    log_debug "Especialista valido: $specialist"
    return 0
}

# Valida se o tipo de modelo e valido
# Uso: validate_model_type "random_forest"
validate_model_type() {
    local model_type="${1:-}"

    if [[ -z "$model_type" ]]; then
        log_error "Tipo de modelo nao especificado"
        return 1
    fi

    if [[ ! " ${VALID_MODEL_TYPES[*]} " =~ " ${model_type} " ]]; then
        log_error "Tipo de modelo invalido: $model_type"
        log_info "Tipos validos: ${VALID_MODEL_TYPES[*]}"
        return 1
    fi

    log_debug "Tipo de modelo valido: $model_type"
    return 0
}

# Valida se o provider LLM e valido
# Uso: validate_llm_provider "openai"
validate_llm_provider() {
    local provider="${1:-}"

    if [[ -z "$provider" ]]; then
        log_error "Provider LLM nao especificado"
        return 1
    fi

    if [[ ! " ${VALID_LLM_PROVIDERS[*]} " =~ " ${provider} " ]]; then
        log_error "Provider LLM invalido: $provider"
        log_info "Providers validos: ${VALID_LLM_PROVIDERS[*]}"
        return 1
    fi

    log_debug "Provider LLM valido: $provider"
    return 0
}

# ============================================================================
# Funcoes de Verificacao de Conexao
# ============================================================================

# Verifica conectividade com MLflow
# Uso: check_mlflow_connection
check_mlflow_connection() {
    local mlflow_uri="${MLFLOW_URI:-http://mlflow.mlflow:5000}"

    log_debug "Verificando conexao com MLflow: $mlflow_uri"

    if ! curl -sf "$mlflow_uri/health" > /dev/null 2>&1; then
        # Tentar endpoint alternativo
        if ! curl -sf "$mlflow_uri/api/2.0/mlflow/experiments/list" > /dev/null 2>&1; then
            log_error "MLflow nao acessivel em $mlflow_uri"
            log_info "Dicas:"
            log_info "  - Verifique se o MLflow esta rodando: kubectl get pods -n mlflow"
            log_info "  - Port-forward: kubectl port-forward -n mlflow svc/mlflow 5000:5000"
            log_info "  - Defina MLFLOW_URI: export MLFLOW_URI=http://localhost:5000"
            return 1
        fi
    fi

    log_success "MLflow conectado: $mlflow_uri"
    return 0
}

# Verifica conectividade com MongoDB
# Uso: check_mongodb_connection
check_mongodb_connection() {
    local mongodb_uri="${MONGODB_URI:-mongodb://localhost:27017}"

    log_debug "Verificando conexao com MongoDB..."

    # Verificar se mongosh esta disponivel
    if ! command -v mongosh &> /dev/null; then
        log_warning "mongosh nao disponivel, feedbacks humanos nao serao incluidos"
        return 1
    fi

    # Tentar ping no MongoDB
    if ! mongosh "$mongodb_uri" --quiet --eval "db.runCommand({ ping: 1 })" > /dev/null 2>&1; then
        log_warning "MongoDB nao acessivel, feedbacks humanos nao serao incluidos"
        return 1
    fi

    log_success "MongoDB conectado"
    return 0
}

# Verifica conectividade com Kubernetes
# Uso: check_kubernetes_connection
check_kubernetes_connection() {
    log_debug "Verificando conexao com Kubernetes..."

    if ! command -v kubectl &> /dev/null; then
        log_warning "kubectl nao disponivel"
        return 1
    fi

    if ! kubectl version --short > /dev/null 2>&1; then
        log_warning "kubectl nao consegue conectar ao cluster"
        return 1
    fi

    log_success "Kubernetes conectado"
    return 0
}

# ============================================================================
# Funcoes de Obtencao de Configuracao
# ============================================================================

# Obtem URI do MLflow de variaveis de ambiente
# Uso: get_mlflow_uri
get_mlflow_uri() {
    local uri="${MLFLOW_URI:-}"

    # Tentar obter do ConfigMap se nao definido
    if [[ -z "$uri" ]] && command -v kubectl &> /dev/null; then
        uri=$(kubectl get configmap ml-config -n mlflow -o jsonpath='{.data.MLFLOW_TRACKING_URI}' 2>/dev/null || echo "")
    fi

    # Fallback para valor padrao
    if [[ -z "$uri" ]]; then
        uri="http://mlflow.mlflow:5000"
    fi

    echo "$uri"
}

# Obtem URI do MongoDB de variaveis de ambiente
# Uso: get_mongodb_uri
get_mongodb_uri() {
    local uri="${MONGODB_URI:-}"

    # Tentar obter do Secret se nao definido
    if [[ -z "$uri" ]] && command -v kubectl &> /dev/null; then
        uri=$(kubectl get secret mongodb-secret -n data-layer -o jsonpath='{.data.uri}' 2>/dev/null | base64 -d 2>/dev/null || echo "")
    fi

    # Fallback para valor padrao
    if [[ -z "$uri" ]]; then
        uri="mongodb://localhost:27017"
    fi

    echo "$uri"
}

# Obtem diretorio de datasets
# Uso: get_dataset_dir
get_dataset_dir() {
    local dir="${DATASET_DIR:-}"

    # Fallback para diretorio padrao
    if [[ -z "$dir" ]]; then
        dir="/data/training"
    fi

    # Verificar se diretorio existe
    if [[ ! -d "$dir" ]]; then
        # Tentar diretorio local do projeto
        local project_dir
        project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
        if [[ -d "$project_dir/ml_pipelines/training/data" ]]; then
            dir="$project_dir/ml_pipelines/training/data"
        fi
    fi

    echo "$dir"
}

# ============================================================================
# Funcoes de Pre-Flight Checks
# ============================================================================

# Executa verificacoes pre-treinamento
# Uso: preflight_checks_training [specialist]
preflight_checks_training() {
    local specialist="${1:-all}"

    log_section "Pre-Flight Checks"

    local errors=0

    # Verificar MLflow (obrigatorio)
    if ! check_mlflow_connection; then
        ((errors++))
    fi

    # Verificar MongoDB (opcional para feedbacks)
    check_mongodb_connection || true

    # Verificar datasets
    local dataset_dir
    dataset_dir=$(get_dataset_dir)

    if [[ "$specialist" == "all" ]]; then
        local found=0
        for spec in "${VALID_SPECIALISTS[@]}"; do
            local dataset_file="$dataset_dir/specialist_${spec}_base.parquet"
            if [[ -f "$dataset_file" ]]; then
                ((found++))
                log_debug "Dataset encontrado: $dataset_file"
            else
                log_warning "Dataset nao encontrado: $dataset_file"
            fi
        done

        if [[ $found -eq 0 ]]; then
            log_warning "Nenhum dataset encontrado em $dataset_dir"
            log_info "Use 'ml.sh generate-dataset --all' para gerar datasets"
        else
            log_success "Datasets encontrados: $found/${#VALID_SPECIALISTS[@]}"
        fi
    else
        local dataset_file="$dataset_dir/specialist_${specialist}_base.parquet"
        if [[ ! -f "$dataset_file" ]]; then
            log_warning "Dataset nao encontrado: $dataset_file"
            log_info "Use 'ml.sh generate-dataset --specialist $specialist' para gerar"
        else
            log_success "Dataset encontrado: $dataset_file"
        fi
    fi

    if [[ $errors -gt 0 ]]; then
        log_error "Pre-flight checks falharam com $errors erro(s)"
        return 1
    fi

    log_success "Pre-flight checks concluidos"
    return 0
}

# ============================================================================
# Funcoes Utilitarias
# ============================================================================

# Formata duracao em segundos para formato legivel
# Uso: format_duration 125
format_duration() {
    local seconds="${1:-0}"

    if [[ $seconds -lt 60 ]]; then
        echo "${seconds}s"
    elif [[ $seconds -lt 3600 ]]; then
        local mins=$((seconds / 60))
        local secs=$((seconds % 60))
        echo "${mins}m ${secs}s"
    else
        local hours=$((seconds / 3600))
        local mins=$(((seconds % 3600) / 60))
        echo "${hours}h ${mins}m"
    fi
}

# Verifica se comando existe
# Uso: require_command "python3"
require_command() {
    local cmd="$1"
    local msg="${2:-Comando '$cmd' nao encontrado}"

    if ! command -v "$cmd" &> /dev/null; then
        log_error "$msg"
        return 1
    fi

    return 0
}

# Aguarda com feedback visual
# Uso: wait_with_progress 5 "Aguardando..."
wait_with_progress() {
    local seconds="$1"
    local message="${2:-Aguardando}"

    for ((i=seconds; i>0; i--)); do
        printf "\r%s %ds...   " "$message" "$i" >&2
        sleep 1
    done
    printf "\r%s                    \n" "" >&2
}

# Exportar funcoes
export -f validate_specialist_type validate_model_type validate_llm_provider
export -f check_mlflow_connection check_mongodb_connection check_kubernetes_connection
export -f get_mlflow_uri get_mongodb_uri get_dataset_dir
export -f preflight_checks_training
export -f format_duration require_command wait_with_progress
