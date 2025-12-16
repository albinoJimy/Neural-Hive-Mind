#!/bin/bash
set -euo pipefail

# ============================================================================
# AVISO DE DEPRECACAO
# Este script sera descontinuado em breve.
# Use o novo CLI unificado: ml.sh retrain --specialist TYPE
# ============================================================================
if [[ "${ML_CLI_WRAPPER:-false}" != "true" ]]; then
    echo ""
    echo "AVISO: Este script sera descontinuado."
    echo "       Use o novo CLI unificado: ml.sh retrain --specialist TYPE"
    echo ""
    sleep 2
fi

# retrain_specialist.sh - Re-treinar especialista especifico com opcoes customizadas
# Uso: ./retrain_specialist.sh --specialist TYPE [OPCOES]

# Configuracao
MLFLOW_URI="${MLFLOW_URI:-http://mlflow.mlflow:5000}"
MONGODB_URI="${MONGODB_URI:-mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin}"
DATASET_DIR="${DATASET_DIR:-/data/training}"
K8S_NAMESPACE="${K8S_NAMESPACE:-semantic-translation}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"

# Opções padrão
SPECIALIST=""
MODEL_TYPE="random_forest"
HYPERPARAMETER_TUNING=false
PROVIDER="${DATASET_PROVIDER:-openai}"
FORCE_RETRAIN=false
DRY_RUN=false

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Função de uso
usage() {
    cat << EOF
Uso: $0 --specialist TYPE [OPÇÕES]

Re-treina especialista específico com opções customizadas.

OPÇÕES OBRIGATÓRIAS:
    --specialist TYPE        Tipo do especialista (technical|business|behavior|evolution|architecture)

OPÇÕES OPCIONAIS:
    --model-type TYPE        Tipo de modelo: random_forest (padrão), gradient_boosting, neural_network
    --hyperparameter-tuning  Habilitar GridSearchCV (padrão: false)
    --provider PROVIDER      Provider LLM para geração de dataset: openai (padrão), anthropic, ollama
                             Pode ser definido via variável de ambiente DATASET_PROVIDER
    --force-retrain          Forçar re-treino mesmo se modelo atual for bom
    --dry-run                Simular treinamento sem registrar no MLflow
    -h, --help               Mostrar esta mensagem

NOTA: Promoção automática é sempre habilitada quando thresholds são atingidos.
      Janela de feedbacks e qualidade mínima ainda não estão implementadas.

EXEMPLOS:
    $0 --specialist technical
    $0 --specialist business --hyperparameter-tuning --model-type gradient_boosting
    $0 --specialist behavior --force-retrain --provider anthropic
    $0 --specialist evolution --dry-run --provider ollama

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
        --model-type)
            MODEL_TYPE="$2"
            shift 2
            ;;
        --hyperparameter-tuning)
            HYPERPARAMETER_TUNING=true
            shift
            ;;
        --provider)
            PROVIDER="$2"
            shift 2
            ;;
        --force-retrain)
            FORCE_RETRAIN=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Erro: Opção desconhecida: $1${NC}" >&2
            usage
            ;;
    esac
done

# Validar argumentos obrigatórios
if [[ -z "$SPECIALIST" ]]; then
    echo -e "${RED}Erro: --specialist é obrigatório${NC}" >&2
    usage
fi

# Validar especialista
SPECIALISTS=("technical" "business" "behavior" "evolution" "architecture")
if [[ ! " ${SPECIALISTS[@]} " =~ " ${SPECIALIST} " ]]; then
    echo -e "${RED}Erro: Especialista inválido: $SPECIALIST${NC}" >&2
    echo -e "Especialistas válidos: ${SPECIALISTS[*]}" >&2
    exit 1
fi

# Validar model_type
MODEL_TYPES=("random_forest" "gradient_boosting" "neural_network")
if [[ ! " ${MODEL_TYPES[@]} " =~ " ${MODEL_TYPE} " ]]; then
    echo -e "${RED}Erro: Tipo de modelo inválido: $MODEL_TYPE${NC}" >&2
    echo -e "Tipos válidos: ${MODEL_TYPES[*]}" >&2
    exit 1
fi

# Validar provider
PROVIDERS=("openai" "anthropic" "ollama")
if [[ ! " ${PROVIDERS[@]} " =~ " ${PROVIDER} " ]]; then
    echo -e "${RED}Erro: Provider inválido: $PROVIDER${NC}" >&2
    echo -e "Providers válidos: ${PROVIDERS[*]}" >&2
    exit 1
fi

# Criar diretório de logs
mkdir -p "$LOG_DIR"

# Arquivo de log
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
LOG_FILE="$LOG_DIR/retrain_${SPECIALIST}_${TIMESTAMP}.log"

# Função de log
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

# Pre-flight checks
preflight_checks() {
    log "${BLUE}=== Pre-flight Checks ===${NC}"

    # Verificar MLflow
    if ! curl -sf "$MLFLOW_URI/health" > /dev/null 2>&1; then
        log "${RED}❌ MLflow não acessível em $MLFLOW_URI${NC}"
        log "${YELLOW}Dica: kubectl get pods -n mlflow${NC}"
        exit 2
    fi
    log "${GREEN}✓ MLflow acessível${NC}"

    # Verificar MongoDB (warning apenas, feedback é opcional)
    if ! command -v mongosh &> /dev/null; then
        log "${YELLOW}⚠️  mongosh não disponível, feedbacks não serão incluídos${NC}"
    else
        if ! mongosh "$MONGODB_URI" --eval "db.runCommand({ ping: 1 })" > /dev/null 2>&1; then
            log "${YELLOW}⚠️  MongoDB não acessível, feedbacks não serão incluídos${NC}"
        else
            log "${GREEN}✓ MongoDB acessível${NC}"
        fi
    fi

    # Verificar dataset
    local dataset_file="$DATASET_DIR/specialist_${SPECIALIST}_base.parquet"
    if [[ ! -f "$dataset_file" ]]; then
        log "${RED}❌ Dataset não encontrado: $dataset_file${NC}"
        log "${YELLOW}Deseja gerar novo dataset com IA? (y/n)${NC}"
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            log "${BLUE}Gerando dataset para $SPECIALIST com provider $PROVIDER...${NC}"
            cd "$(dirname "$SCRIPT_DIR")/training"
            python3 generate_training_datasets.py \
                --specialist-type "$SPECIALIST" \
                --provider "$PROVIDER" \
                --num-examples 1000 | tee -a "$LOG_FILE"

            if [[ ! -f "$dataset_file" ]]; then
                log "${RED}❌ Falha ao gerar dataset${NC}"
                exit 1
            fi
        else
            log "${RED}❌ Dataset necessário para treinamento${NC}"
            exit 1
        fi
    fi
    log "${GREEN}✓ Dataset encontrado: $dataset_file${NC}"

    log ""
}

# Análise de necessidade de re-treino
analyze_retrain_necessity() {
    if [[ "$FORCE_RETRAIN" == "true" ]]; then
        log "${YELLOW}⚠️  --force-retrain ativado, pulando análise de necessidade${NC}"
        return 0
    fi

    log "${BLUE}=== Análise de Necessidade de Re-treino ===${NC}"

    # Query modelo atual em Production
    local model_name="${SPECIALIST}-evaluator"
    local response
    response=$(curl -sf "$MLFLOW_URI/api/2.0/mlflow/model-versions/search?filter=name='$model_name'" 2>/dev/null || echo "{}")

    local prod_version
    prod_version=$(echo "$response" | jq -r '.model_versions[] | select(.current_stage=="Production") | .version' 2>/dev/null | head -n 1)

    if [[ -z "$prod_version" ]] || [[ "$prod_version" == "null" ]]; then
        log "${YELLOW}⚠️  Nenhum modelo em Production, re-treino necessário${NC}"
        return 0
    fi

    # Obter métricas e timestamp
    local run_id timestamp
    run_id=$(echo "$response" | jq -r ".model_versions[] | select(.version==\"$prod_version\") | .run_id" 2>/dev/null)
    timestamp=$(echo "$response" | jq -r ".model_versions[] | select(.version==\"$prod_version\") | .last_updated_timestamp" 2>/dev/null)

    # Obter métricas do run
    local run_response
    run_response=$(curl -sf "$MLFLOW_URI/api/2.0/mlflow/runs/get?run_id=$run_id" 2>/dev/null || echo "{}")

    local precision recall f1
    precision=$(echo "$run_response" | jq -r '.run.data.metrics[] | select(.key=="precision") | .value' 2>/dev/null || echo "0")
    recall=$(echo "$run_response" | jq -r '.run.data.metrics[] | select(.key=="recall") | .value' 2>/dev/null || echo "0")
    f1=$(echo "$run_response" | jq -r '.run.data.metrics[] | select(.key=="f1") | .value' 2>/dev/null || echo "0")

    log "${BLUE}Modelo atual em Production:${NC}"
    log "  Versão: v$prod_version"
    log "  Precision: $precision"
    log "  Recall: $recall"
    log "  F1 Score: $f1"

    # Calcular dias desde última atualização
    if [[ -n "$timestamp" ]] && [[ "$timestamp" != "null" ]]; then
        local days_since_update
        local timestamp_sec=$((timestamp / 1000))
        local current_sec=$(date +%s)
        days_since_update=$(( (current_sec - timestamp_sec) / 86400 ))
        log "  Última atualização: $days_since_update dias atrás"

        # Verificar se modelo é excelente e recente
        if (( $(echo "$precision > 0.90" | bc -l 2>/dev/null || echo "0") )) && \
           (( $(echo "$f1 > 0.88" | bc -l 2>/dev/null || echo "0") )) && \
           [[ $days_since_update -lt 7 ]]; then
            log ""
            log "${YELLOW}⚠️  Modelo atual tem métricas excelentes e foi atualizado recentemente${NC}"
            log "${YELLOW}Continuar com re-treino? (y/n)${NC}"
            read -r response
            if [[ ! "$response" =~ ^[Yy]$ ]]; then
                log "${BLUE}Re-treino cancelado pelo usuário${NC}"
                exit 0
            fi
        fi
    fi

    log ""
}

# Executar treinamento
execute_training() {
    log "${BLUE}=== Executando Treinamento ===${NC}"
    log "Especialista: $SPECIALIST"
    log "Tipo de modelo: $MODEL_TYPE"
    log "Hyperparameter tuning: $HYPERPARAMETER_TUNING"
    log "Dry-run: $DRY_RUN"
    log ""

    # Construir comando
    local cmd="python3 $(dirname "$SCRIPT_DIR")/training/train_specialist_model.py"
    cmd="$cmd --specialist-type $SPECIALIST"
    cmd="$cmd --model-type $MODEL_TYPE"

    if [[ "$HYPERPARAMETER_TUNING" == "true" ]]; then
        cmd="$cmd --hyperparameter-tuning"
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log "${YELLOW}[DRY-RUN] Comando que seria executado:${NC}"
        log "$cmd"
        return 0
    fi

    # Executar treinamento
    log "${BLUE}Iniciando treinamento...${NC}"
    log "Comando: $cmd"
    log ""

    cd "$(dirname "$SCRIPT_DIR")/training"

    if eval "$cmd" 2>&1 | tee -a "$LOG_FILE"; then
        log ""
        log "${GREEN}✓ Treinamento concluído com sucesso${NC}"
        return 0
    else
        log ""
        log "${RED}❌ Treinamento falhou${NC}"
        exit 1
    fi
}

# Comparação pós-treinamento
post_training_comparison() {
    if [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi

    log "${BLUE}=== Comparação Pós-Treinamento ===${NC}"

    # Query modelo atualizado
    local model_name="${SPECIALIST}-evaluator"
    local response
    response=$(curl -sf "$MLFLOW_URI/api/2.0/mlflow/model-versions/search?filter=name='$model_name'" 2>/dev/null || echo "{}")

    local prod_version staging_version
    prod_version=$(echo "$response" | jq -r '.model_versions[] | select(.current_stage=="Production") | .version' 2>/dev/null | head -n 1)
    staging_version=$(echo "$response" | jq -r '.model_versions[] | select(.current_stage=="Staging") | .version' 2>/dev/null | head -n 1)

    # Obter métricas Production
    local prod_metrics=""
    if [[ -n "$prod_version" ]] && [[ "$prod_version" != "null" ]]; then
        local run_id
        run_id=$(echo "$response" | jq -r ".model_versions[] | select(.version==\"$prod_version\") | .run_id" 2>/dev/null)
        local run_response
        run_response=$(curl -sf "$MLFLOW_URI/api/2.0/mlflow/runs/get?run_id=$run_id" 2>/dev/null || echo "{}")

        local precision recall f1 accuracy
        precision=$(echo "$run_response" | jq -r '.run.data.metrics[] | select(.key=="precision") | .value' 2>/dev/null || echo "0")
        recall=$(echo "$run_response" | jq -r '.run.data.metrics[] | select(.key=="recall") | .value' 2>/dev/null || echo "0")
        f1=$(echo "$run_response" | jq -r '.run.data.metrics[] | select(.key=="f1") | .value' 2>/dev/null || echo "0")
        accuracy=$(echo "$run_response" | jq -r '.run.data.metrics[] | select(.key=="accuracy") | .value' 2>/dev/null || echo "0")

        prod_metrics="Precision: $precision, Recall: $recall, F1: $f1, Accuracy: $accuracy"
    fi

    # Obter métricas Staging
    local staging_metrics=""
    if [[ -n "$staging_version" ]] && [[ "$staging_version" != "null" ]]; then
        local run_id
        run_id=$(echo "$response" | jq -r ".model_versions[] | select(.version==\"$staging_version\") | .run_id" 2>/dev/null)
        local run_response
        run_response=$(curl -sf "$MLFLOW_URI/api/2.0/mlflow/runs/get?run_id=$run_id" 2>/dev/null || echo "{}")

        local precision recall f1 accuracy
        precision=$(echo "$run_response" | jq -r '.run.data.metrics[] | select(.key=="precision") | .value' 2>/dev/null || echo "0")
        recall=$(echo "$run_response" | jq -r '.run.data.metrics[] | select(.key=="recall") | .value' 2>/dev/null || echo "0")
        f1=$(echo "$run_response" | jq -r '.run.data.metrics[] | select(.key=="f1") | .value' 2>/dev/null || echo "0")
        accuracy=$(echo "$run_response" | jq -r '.run.data.metrics[] | select(.key=="accuracy") | .value' 2>/dev/null || echo "0")

        staging_metrics="Precision: $precision, Recall: $recall, F1: $f1, Accuracy: $accuracy"
    fi

    log "${BLUE}Production (v$prod_version):${NC} $prod_metrics"
    if [[ -n "$staging_version" ]] && [[ "$staging_version" != "null" ]]; then
        log "${YELLOW}Staging (v$staging_version):${NC} $staging_metrics"
    fi

    # Verificar se foi promovido
    if [[ -n "$prod_version" ]] && [[ "$prod_version" != "null" ]]; then
        local was_promoted=false
        # Se a versão mais recente está em Production, foi promovida
        local latest_version
        latest_version=$(echo "$response" | jq -r '.model_versions | sort_by(.version | tonumber) | reverse | .[0].version' 2>/dev/null)
        if [[ "$latest_version" == "$prod_version" ]]; then
            was_promoted=true
        fi

        if [[ "$was_promoted" == "true" ]]; then
            log "${GREEN}✓ Modelo foi promovido automaticamente para Production${NC}"
        else
            log "${YELLOW}⚠️  Modelo permanece em Staging (não atingiu thresholds)${NC}"
        fi
    fi

    log ""
}

# Ações pós-treinamento
post_training_actions() {
    if [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi

    log "${BLUE}=== Ações Pós-Treinamento ===${NC}"

    # Verificar se kubectl disponível
    if ! command -v kubectl &> /dev/null; then
        log "${YELLOW}⚠️  kubectl não disponível, pule o restart manual${NC}"
        return 0
    fi

    log "${YELLOW}Sugestão: Reiniciar pod de especialista para carregar novo modelo${NC}"
    log "Comando: kubectl rollout restart deployment/specialist-$SPECIALIST -n $K8S_NAMESPACE"
    log ""
    log "Validar carregamento:"
    log "  $(dirname "$SCRIPT_DIR")/training/validate_models_loaded.sh"
    log ""
}

# Main
main() {
    log "${GREEN}=== Re-treino de Especialista ===${NC}"
    log "Timestamp: $TIMESTAMP"
    log "Usuário: ${USER:-unknown}"
    log "Log file: $LOG_FILE"
    log ""

    preflight_checks
    analyze_retrain_necessity
    execute_training
    post_training_comparison
    post_training_actions

    log "${GREEN}=== Re-treino Concluído ===${NC}"
    log "Log completo: $LOG_FILE"
}

main
