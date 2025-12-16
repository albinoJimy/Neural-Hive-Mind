#!/bin/bash
set -euo pipefail

# ============================================================================
# AVISO DE DEPRECACAO
# Este script sera descontinuado em breve.
# Use o novo CLI unificado: ml.sh rollback --specialist TYPE
# ============================================================================
if [[ "${ML_CLI_WRAPPER:-false}" != "true" ]]; then
    echo ""
    echo "AVISO: Este script sera descontinuado."
    echo "       Use o novo CLI unificado: ml.sh rollback --specialist TYPE"
    echo ""
    sleep 2
fi

# rollback_model.sh - Fazer rollback de modelo em Production para versao anterior
# Uso: ./rollback_model.sh --specialist TYPE [OPCOES]

# Configuracao
MLFLOW_URI="${MLFLOW_URI:-http://mlflow.mlflow:5000}"
K8S_NAMESPACE="${K8S_NAMESPACE:-semantic-translation}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"

# Opções padrão
SPECIALIST=""
TO_VERSION=""
FROM_STAGE=""
REASON=""
FORCE=false
DRY_RUN=false
ALL_SPECIALISTS=false

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

Faz rollback de modelo em Production para versão anterior.

OPÇÕES OBRIGATÓRIAS:
    --specialist TYPE    Tipo do especialista (technical|business|behavior|evolution|architecture)

OPÇÕES OPCIONAIS:
    --to-version N       Versão específica para rollback (padrão: versão anterior à Production atual)
    --from-stage STAGE   Stage de onde pegar versão: Staging, Archived (padrão: última antes de Production)
    --reason TEXT        Motivo do rollback (para auditoria)
    --force              Não pedir confirmação
    --dry-run            Simular rollback sem executar
    --all                Rollback de todos os 5 especialistas
    -h, --help           Mostrar esta mensagem

EXEMPLOS:
    $0 --specialist technical --reason "High latency in production"
    $0 --specialist business --to-version 3 --reason "Regression in accuracy"
    $0 --specialist behavior --force
    $0 --all --reason "Emergency rollback after deployment"

EXIT CODES:
    0  Rollback executado com sucesso
    1  Erro de validação (modelo não existe, versão não encontrada)
    2  MLflow não acessível
    3  Usuário cancelou operação

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
        --to-version)
            TO_VERSION="$2"
            shift 2
            ;;
        --from-stage)
            FROM_STAGE="$2"
            shift 2
            ;;
        --reason)
            REASON="$2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --all)
            ALL_SPECIALISTS=true
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

# Validar argumentos
if [[ -z "$SPECIALIST" ]] && [[ "$ALL_SPECIALISTS" == "false" ]]; then
    echo -e "${RED}Erro: --specialist ou --all é obrigatório${NC}" >&2
    usage
fi

# Validar especialista se especificado
SPECIALISTS=("technical" "business" "behavior" "evolution" "architecture")
if [[ -n "$SPECIALIST" ]]; then
    if [[ ! " ${SPECIALISTS[@]} " =~ " ${SPECIALIST} " ]]; then
        echo -e "${RED}Erro: Especialista inválido: $SPECIALIST${NC}" >&2
        echo -e "Especialistas válidos: ${SPECIALISTS[*]}" >&2
        exit 1
    fi
fi

# Criar diretório de logs
mkdir -p "$LOG_DIR"

# Arquivo de log
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
LOG_FILE="$LOG_DIR/rollback_${SPECIALIST:-all}_${TIMESTAMP}.log"

# Função de log
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

# Verificar MLflow
check_mlflow_health() {
    if ! curl -sf "$MLFLOW_URI/health" > /dev/null 2>&1; then
        log "${RED}❌ MLflow não acessível em $MLFLOW_URI${NC}"
        log "${YELLOW}Dica: kubectl get pods -n mlflow${NC}"
        exit 2
    fi
}

# Validações pré-rollback
validate_rollback() {
    local specialist=$1
    local model_name="${specialist}-evaluator"

    log "${BLUE}=== Validações Pré-Rollback ===${NC}"
    log "Especialista: $specialist"
    log "Modelo: $model_name"
    log ""

    # Verificar se modelo existe
    local response
    response=$(curl -sf "$MLFLOW_URI/api/2.0/mlflow/registered-models/get?name=$model_name" 2>/dev/null || echo "{}")

    if ! echo "$response" | jq -e '.registered_model' > /dev/null 2>&1; then
        log "${RED}❌ Modelo não encontrado: $model_name${NC}"
        return 1
    fi

    # Obter versões
    local versions
    versions=$(curl -sf "$MLFLOW_URI/api/2.0/mlflow/model-versions/search?filter=name='$model_name'" 2>/dev/null || echo "{}")

    # Identificar versão atual em Production
    local current_prod_version
    current_prod_version=$(echo "$versions" | jq -r '.model_versions[] | select(.current_stage=="Production") | .version' 2>/dev/null | head -n 1)

    if [[ -z "$current_prod_version" ]] || [[ "$current_prod_version" == "null" ]]; then
        log "${RED}❌ Nenhuma versão em Production atualmente${NC}"
        return 1
    fi

    log "${BLUE}Versão atual em Production:${NC} v$current_prod_version"

    # Identificar versão de destino
    local target_version="$TO_VERSION"

    if [[ -z "$target_version" ]]; then
        # Buscar última versão antes da atual Production
        if [[ -n "$FROM_STAGE" ]]; then
            target_version=$(echo "$versions" | jq -r ".model_versions[] | select(.current_stage==\"$FROM_STAGE\") | .version" 2>/dev/null | head -n 1)
        else
            # Buscar qualquer versão anterior (por número de versão)
            target_version=$(echo "$versions" | jq -r --argjson current "$current_prod_version" '.model_versions[] | select((.version | tonumber) < $current) | .version' 2>/dev/null | sort -rn | head -n 1)
        fi
    fi

    if [[ -z "$target_version" ]] || [[ "$target_version" == "null" ]]; then
        log "${RED}❌ Nenhuma versão de destino encontrada${NC}"
        if [[ -n "$FROM_STAGE" ]]; then
            log "${YELLOW}Dica: Verifique se existe versão em stage '$FROM_STAGE'${NC}"
        fi
        return 1
    fi

    # Verificar se versão de destino existe
    local target_exists
    target_exists=$(echo "$versions" | jq -r ".model_versions[] | select(.version==\"$target_version\") | .version" 2>/dev/null)

    if [[ -z "$target_exists" ]] || [[ "$target_exists" == "null" ]]; then
        log "${RED}❌ Versão de destino não encontrada: v$target_version${NC}"
        return 1
    fi

    log "${GREEN}✓ Versão de destino encontrada:${NC} v$target_version"
    log ""

    # Retornar versões via stdout para captura
    echo "$current_prod_version:$target_version:$versions"
}

# Análise de impacto
analyze_impact() {
    local specialist=$1
    local current_version=$2
    local target_version=$3
    local versions=$4

    log "${BLUE}=== Análise de Impacto ===${NC}"

    # Obter métricas da versão atual
    local current_run_id
    current_run_id=$(echo "$versions" | jq -r ".model_versions[] | select(.version==\"$current_version\") | .run_id" 2>/dev/null)

    local current_metrics=""
    local current_f1="0"
    if [[ -n "$current_run_id" ]] && [[ "$current_run_id" != "null" ]]; then
        local current_run_response
        current_run_response=$(curl -sf "$MLFLOW_URI/api/2.0/mlflow/runs/get?run_id=$current_run_id" 2>/dev/null || echo "{}")

        local precision recall f1 accuracy
        precision=$(echo "$current_run_response" | jq -r '.run.data.metrics[] | select(.key=="precision") | .value' 2>/dev/null || echo "N/A")
        recall=$(echo "$current_run_response" | jq -r '.run.data.metrics[] | select(.key=="recall") | .value' 2>/dev/null || echo "N/A")
        f1=$(echo "$current_run_response" | jq -r '.run.data.metrics[] | select(.key=="f1") | .value' 2>/dev/null || echo "N/A")
        accuracy=$(echo "$current_run_response" | jq -r '.run.data.metrics[] | select(.key=="accuracy") | .value' 2>/dev/null || echo "N/A")

        current_metrics="Precision: $precision, Recall: $recall, F1: $f1, Accuracy: $accuracy"
        current_f1="$f1"
    fi

    # Obter métricas da versão de destino
    local target_run_id
    target_run_id=$(echo "$versions" | jq -r ".model_versions[] | select(.version==\"$target_version\") | .run_id" 2>/dev/null)

    local target_metrics=""
    local target_precision target_recall target_f1 target_accuracy
    if [[ -n "$target_run_id" ]] && [[ "$target_run_id" != "null" ]]; then
        local target_run_response
        target_run_response=$(curl -sf "$MLFLOW_URI/api/2.0/mlflow/runs/get?run_id=$target_run_id" 2>/dev/null || echo "{}")

        target_precision=$(echo "$target_run_response" | jq -r '.run.data.metrics[] | select(.key=="precision") | .value' 2>/dev/null || echo "N/A")
        target_recall=$(echo "$target_run_response" | jq -r '.run.data.metrics[] | select(.key=="recall") | .value' 2>/dev/null || echo "N/A")
        target_f1=$(echo "$target_run_response" | jq -r '.run.data.metrics[] | select(.key=="f1") | .value' 2>/dev/null || echo "N/A")
        target_accuracy=$(echo "$target_run_response" | jq -r '.run.data.metrics[] | select(.key=="accuracy") | .value' 2>/dev/null || echo "N/A")

        target_metrics="Precision: $target_precision, Recall: $target_recall, F1: $target_f1, Accuracy: $target_accuracy"
    fi

    # Timestamps
    local current_timestamp target_timestamp
    current_timestamp=$(echo "$versions" | jq -r ".model_versions[] | select(.version==\"$current_version\") | .creation_timestamp" 2>/dev/null)
    target_timestamp=$(echo "$versions" | jq -r ".model_versions[] | select(.version==\"$target_version\") | .creation_timestamp" 2>/dev/null)

    if [[ -n "$current_timestamp" ]] && [[ "$current_timestamp" != "null" ]]; then
        current_timestamp=$(date -d "@$((current_timestamp / 1000))" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "$current_timestamp")
    fi
    if [[ -n "$target_timestamp" ]] && [[ "$target_timestamp" != "null" ]]; then
        target_timestamp=$(date -d "@$((target_timestamp / 1000))" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "$target_timestamp")
    fi

    log "${BLUE}Current Production (v$current_version):${NC}"
    log "  Criado em: $current_timestamp"
    log "  Métricas: $current_metrics"
    log ""
    log "${YELLOW}Target Version (v$target_version):${NC}"
    log "  Criado em: $target_timestamp"
    log "  Métricas: $target_metrics"
    log ""

    # Calcular delta de performance
    if [[ "$current_metrics" != "" ]] && [[ "$target_metrics" != "" ]]; then
        # Usar F1 já extraídos das variáveis locais
        local target_f1_num="$target_f1"

        # Validar que ambos F1 são numéricos
        if [[ "$target_f1_num" != "N/A" ]] && [[ "$target_f1_num" != "null" ]] && \
           [[ "$current_f1" != "N/A" ]] && [[ "$current_f1" != "null" ]] && \
           [[ "$current_f1" != "0" ]]; then
            # Comparar versões usando bc
            if command -v bc &> /dev/null; then
                local delta
                delta=$(echo "scale=2; ($target_f1_num - $current_f1) / $current_f1 * 100" | bc -l 2>/dev/null || echo "0")

                log "${BLUE}Performance Delta:${NC}"
                if (( $(echo "$delta < 0" | bc -l 2>/dev/null || echo "0") )); then
                    log "${RED}⚠️  WARNING: Este rollback resultará em degradação de ${delta#-}% em F1 Score${NC}"
                else
                    log "${GREEN}✓ Rollback melhorará performance em +${delta}% em F1 Score${NC}"
                fi
                log ""
            fi
        fi
    fi
}

# Confirmação interativa
confirm_rollback() {
    local specialist=$1
    local current_version=$2
    local target_version=$3

    if [[ "$FORCE" == "true" ]] || [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi

    log "${YELLOW}=== Resumo do Rollback ===${NC}"
    log "Specialist: $specialist"
    log "Current Production: v$current_version"
    log "Target Version: v$target_version"
    log "Reason: ${REASON:-Not specified}"
    log ""
    log "${YELLOW}Continuar com rollback? [y/N]:${NC}"

    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        log "${BLUE}Rollback cancelado pelo usuário${NC}"
        exit 3
    fi
}

# Executar rollback
execute_rollback() {
    local specialist=$1
    local current_version=$2
    local target_version=$3
    local model_name="${specialist}-evaluator"

    log "${BLUE}=== Executando Rollback ===${NC}"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "${YELLOW}[DRY-RUN] Rollback não será executado (modo simulação)${NC}"
        log "Ações que seriam executadas:"
        log "  1. Transicionar v$current_version de Production para Archived"
        log "  2. Transicionar v$target_version para Production"
        log "  3. Adicionar tags no MLflow para auditoria"
        return 0
    fi

    # Transicionar versão atual para Archived
    log "${BLUE}1. Arquivando versão atual (v$current_version)...${NC}"
    local response
    response=$(curl -sf -X POST "$MLFLOW_URI/api/2.0/mlflow/model-versions/transition-stage" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"$model_name\",
            \"version\": \"$current_version\",
            \"stage\": \"Archived\",
            \"archive_existing_versions\": false
        }" 2>/dev/null || echo "{}")

    if ! echo "$response" | jq -e '.model_version' > /dev/null 2>&1; then
        log "${RED}❌ Falha ao arquivar versão atual${NC}"
        log "Response: $response"
        exit 1
    fi
    log "${GREEN}✓ Versão v$current_version arquivada${NC}"

    # Transicionar versão de destino para Production
    log "${BLUE}2. Promovendo versão de destino (v$target_version) para Production...${NC}"
    response=$(curl -sf -X POST "$MLFLOW_URI/api/2.0/mlflow/model-versions/transition-stage" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"$model_name\",
            \"version\": \"$target_version\",
            \"stage\": \"Production\",
            \"archive_existing_versions\": false
        }" 2>/dev/null || echo "{}")

    if ! echo "$response" | jq -e '.model_version' > /dev/null 2>&1; then
        log "${RED}❌ Falha ao promover versão de destino${NC}"
        log "Response: $response"
        exit 1
    fi
    log "${GREEN}✓ Versão v$target_version promovida para Production${NC}"

    # Adicionar tags para auditoria
    log "${BLUE}3. Adicionando tags de auditoria...${NC}"
    curl -sf -X POST "$MLFLOW_URI/api/2.0/mlflow/model-versions/set-tag" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"$model_name\",
            \"version\": \"$target_version\",
            \"key\": \"rollback_from\",
            \"value\": \"v$current_version\"
        }" > /dev/null 2>&1

    if [[ -n "$REASON" ]]; then
        curl -sf -X POST "$MLFLOW_URI/api/2.0/mlflow/model-versions/set-tag" \
            -H "Content-Type: application/json" \
            -d "{
                \"name\": \"$model_name\",
                \"version\": \"$target_version\",
                \"key\": \"rollback_reason\",
                \"value\": \"$REASON\"
            }" > /dev/null 2>&1
    fi
    log "${GREEN}✓ Tags de auditoria adicionadas${NC}"

    log ""
    log "${GREEN}✓ Rollback concluído com sucesso${NC}"
}

# Verificação pós-rollback
post_rollback_verification() {
    local specialist=$1
    local target_version=$2
    local model_name="${specialist}-evaluator"

    if [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi

    log "${BLUE}=== Verificação Pós-Rollback ===${NC}"

    # Verificar que versão de destino está em Production
    local response
    response=$(curl -sf "$MLFLOW_URI/api/2.0/mlflow/model-versions/search?filter=name='$model_name'" 2>/dev/null || echo "{}")

    local current_prod
    current_prod=$(echo "$response" | jq -r '.model_versions[] | select(.current_stage=="Production") | .version' 2>/dev/null | head -n 1)

    if [[ "$current_prod" == "$target_version" ]]; then
        log "${GREEN}✓ Versão v$target_version confirmada em Production${NC}"
    else
        log "${RED}❌ ERRO: Versão em Production ($current_prod) não corresponde à esperada ($target_version)${NC}"
        exit 1
    fi

    # Sugerir restart de pods
    log ""
    log "${YELLOW}Ação recomendada: Reiniciar pod de especialista para carregar nova versão${NC}"
    log "Comando: kubectl rollout restart deployment/specialist-$specialist -n $K8S_NAMESPACE"
    log ""
    log "Validar carregamento:"
    log "  $(dirname "$SCRIPT_DIR")/training/validate_models_loaded.sh"
    log ""
}

# Processar um especialista
process_specialist() {
    local specialist=$1

    log "${GREEN}=== Rollback: $specialist ===${NC}"
    log ""

    # Validações
    local validation_output
    validation_output=$(validate_rollback "$specialist")
    if [[ $? -ne 0 ]]; then
        log "${RED}❌ Validação falhou para $specialist${NC}"
        return 1
    fi

    # Parse output
    local current_version target_version versions
    IFS=':' read -r current_version target_version versions <<< "$validation_output"

    # Análise de impacto
    analyze_impact "$specialist" "$current_version" "$target_version" "$versions"

    # Confirmação
    confirm_rollback "$specialist" "$current_version" "$target_version"

    # Executar rollback
    execute_rollback "$specialist" "$current_version" "$target_version"

    # Verificação pós-rollback
    post_rollback_verification "$specialist" "$target_version"

    log ""
}

# Main
main() {
    log "${GREEN}=== Rollback de Modelo ML ===${NC}"
    log "Timestamp: $TIMESTAMP"
    log "Usuário: ${USER:-unknown}"
    log "Log file: $LOG_FILE"
    log ""

    # Verificar MLflow
    check_mlflow_health

    # Processar especialistas
    if [[ "$ALL_SPECIALISTS" == "true" ]]; then
        for spec in "${SPECIALISTS[@]}"; do
            process_specialist "$spec"
        done
    else
        process_specialist "$SPECIALIST"
    fi

    log "${GREEN}=== Rollback Concluído ===${NC}"
    log "Log completo: $LOG_FILE"
}

main
