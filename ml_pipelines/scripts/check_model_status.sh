#!/bin/bash
set -euo pipefail

# ============================================================================
# AVISO DE DEPRECACAO
# Este script sera descontinuado em breve.
# Use o novo CLI unificado: ml.sh status [--all] [--specialist TYPE]
# ============================================================================
if [[ "${ML_CLI_WRAPPER:-false}" != "true" ]]; then
    echo ""
    echo "AVISO: Este script sera descontinuado."
    echo "       Use o novo CLI unificado: ml.sh status --all"
    echo ""
    sleep 2
fi

# check_model_status.sh - Verificar status de modelos no MLflow
# Uso: ./check_model_status.sh [--specialist TYPE] [--all] [--verbose] [--format json|table]

# Configuracao
MLFLOW_URI="${MLFLOW_URI:-http://mlflow.mlflow:5000}"
K8S_NAMESPACE="${K8S_NAMESPACE:-semantic-translation}"
SPECIALISTS=("technical" "business" "behavior" "evolution" "architecture")

# Opções padrão
CHECK_ALL=false
SPECIALIST=""
VERBOSE=false
FORMAT="table"
EXIT_CODE=0

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Função de uso
usage() {
    cat << EOF
Uso: $0 [OPÇÕES]

Verifica status de modelos ML no MLflow Registry.

OPÇÕES:
    --specialist TYPE    Verificar especialista específico (technical|business|behavior|evolution|architecture)
    --all               Verificar todos os 5 especialistas (padrão)
    --verbose           Mostrar informações detalhadas (run_id, timestamps, tags)
    --format FORMAT     Formato de saída: table (padrão) ou json
    -h, --help          Mostrar esta mensagem

EXEMPLOS:
    $0 --all
    $0 --specialist technical --verbose
    $0 --all --format json

EXIT CODES:
    0  Todos os modelos OK
    1  Algum modelo não encontrado ou sem versão em Production
    2  MLflow não acessível

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
            CHECK_ALL=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --format)
            FORMAT="$2"
            shift 2
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

# Default para --all se nenhum especialista especificado
if [[ -z "$SPECIALIST" ]] && [[ "$CHECK_ALL" == "false" ]]; then
    CHECK_ALL=true
fi

# Validar especialista se especificado
if [[ -n "$SPECIALIST" ]]; then
    if [[ ! " ${SPECIALISTS[@]} " =~ " ${SPECIALIST} " ]]; then
        echo -e "${RED}Erro: Especialista inválido: $SPECIALIST${NC}" >&2
        echo -e "Especialistas válidos: ${SPECIALISTS[*]}" >&2
        exit 1
    fi
fi

# Verificar se MLflow está acessível
check_mlflow_health() {
    if ! curl -sf "$MLFLOW_URI/health" > /dev/null 2>&1; then
        echo -e "${RED}❌ Erro: MLflow não acessível em $MLFLOW_URI${NC}" >&2
        echo -e "${YELLOW}Dica: Verifique se o MLflow está rodando:${NC}" >&2
        echo -e "  kubectl get pods -n mlflow" >&2
        echo -e "  kubectl port-forward -n mlflow svc/mlflow 5000:5000" >&2
        return 1
    fi
    return 0
}

# Obter informações de um modelo
get_model_info() {
    local specialist=$1
    local model_name="${specialist}-evaluator"

    # Query MLflow API
    local response
    response=$(curl -sf "$MLFLOW_URI/api/2.0/mlflow/registered-models/get?name=$model_name" 2>/dev/null || echo "{}")

    # Verificar se modelo existe
    if ! echo "$response" | jq -e '.registered_model' > /dev/null 2>&1; then
        echo -e "${RED}⚠️  Modelo não encontrado: $model_name${NC}" >&2
        EXIT_CODE=1
        return 1
    fi

    echo "$response"
}

# Obter versões de um modelo
get_model_versions() {
    local model_name=$1

    local response
    response=$(curl -sf "$MLFLOW_URI/api/2.0/mlflow/model-versions/search?filter=name='$model_name'" 2>/dev/null || echo "{}")

    echo "$response"
}

# Obter métricas de um run
get_run_metrics() {
    local run_id=$1

    local response
    response=$(curl -sf "$MLFLOW_URI/api/2.0/mlflow/runs/get?run_id=$run_id" 2>/dev/null || echo "{}")

    # Extrair métricas
    local precision recall f1 accuracy
    precision=$(echo "$response" | jq -r '.run.data.metrics[] | select(.key=="precision") | .value' 2>/dev/null || echo "N/A")
    recall=$(echo "$response" | jq -r '.run.data.metrics[] | select(.key=="recall") | .value' 2>/dev/null || echo "N/A")
    f1=$(echo "$response" | jq -r '.run.data.metrics[] | select(.key=="f1") | .value' 2>/dev/null || echo "N/A")
    accuracy=$(echo "$response" | jq -r '.run.data.metrics[] | select(.key=="accuracy") | .value' 2>/dev/null || echo "N/A")

    echo "{\"precision\": \"$precision\", \"recall\": \"$recall\", \"f1\": \"$f1\", \"accuracy\": \"$accuracy\"}"
}

# Verificar pod de especialista
check_specialist_pod() {
    local specialist=$1

    if ! command -v kubectl &> /dev/null; then
        return 0  # kubectl não disponível, pular verificação
    fi

    # Verificar se pod está rodando
    local pod_status
    pod_status=$(kubectl get pods -n "$K8S_NAMESPACE" -l "app=specialist-$specialist" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Unknown")

    if [[ "$pod_status" != "Running" ]]; then
        echo -e "${YELLOW}⚠️  Pod specialist-$specialist não está Running (status: $pod_status)${NC}" >&2
    fi

    # Query /status endpoint
    local pod_name
    pod_name=$(kubectl get pods -n "$K8S_NAMESPACE" -l "app=specialist-$specialist" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -n "$pod_name" ]]; then
        local status_response
        status_response=$(kubectl exec -n "$K8S_NAMESPACE" "$pod_name" -- curl -sf http://localhost:8080/status 2>/dev/null || echo "{}")

        local model_loaded
        model_loaded=$(echo "$status_response" | jq -r '.model_loaded' 2>/dev/null || echo "false")

        if [[ "$model_loaded" != "true" ]]; then
            echo -e "${RED}❌ Modelo não carregado pelo pod specialist-$specialist${NC}" >&2
            EXIT_CODE=1
        fi
    fi
}

# Processar um especialista
process_specialist() {
    local specialist=$1
    local model_name="${specialist}-evaluator"

    # Obter informações do modelo
    local model_info
    model_info=$(get_model_info "$specialist")
    if [[ $? -ne 0 ]]; then
        return 1
    fi

    # Obter versões
    local versions
    versions=$(get_model_versions "$model_name")

    # Encontrar versão em Production
    local prod_version
    prod_version=$(echo "$versions" | jq -r '.model_versions[] | select(.current_stage=="Production") | .version' 2>/dev/null | head -n 1)

    # Encontrar versão em Staging
    local staging_version
    staging_version=$(echo "$versions" | jq -r '.model_versions[] | select(.current_stage=="Staging") | .version' 2>/dev/null | head -n 1)

    if [[ -z "$prod_version" ]]; then
        echo -e "${RED}❌ Nenhuma versão em Production para $specialist${NC}" >&2
        EXIT_CODE=1
        prod_version="N/A"
    fi

    # Obter métricas da versão em Production
    local prod_metrics="N/A"
    local prod_run_id=""
    local prod_timestamp=""

    if [[ "$prod_version" != "N/A" ]]; then
        prod_run_id=$(echo "$versions" | jq -r ".model_versions[] | select(.version==\"$prod_version\") | .run_id" 2>/dev/null)
        prod_timestamp=$(echo "$versions" | jq -r ".model_versions[] | select(.version==\"$prod_version\") | .last_updated_timestamp" 2>/dev/null)

        # Converter timestamp de milissegundos para formato legível
        if [[ -n "$prod_timestamp" ]] && [[ "$prod_timestamp" != "null" ]]; then
            prod_timestamp=$(date -d "@$((prod_timestamp / 1000))" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "$prod_timestamp")
        fi

        if [[ -n "$prod_run_id" ]] && [[ "$prod_run_id" != "null" ]]; then
            prod_metrics=$(get_run_metrics "$prod_run_id")
        fi
    fi

    # Obter métricas da versão em Staging
    local staging_metrics="N/A"
    local staging_run_id=""

    if [[ -n "$staging_version" ]] && [[ "$staging_version" != "null" ]]; then
        staging_run_id=$(echo "$versions" | jq -r ".model_versions[] | select(.version==\"$staging_version\") | .run_id" 2>/dev/null)

        if [[ -n "$staging_run_id" ]] && [[ "$staging_run_id" != "null" ]]; then
            staging_metrics=$(get_run_metrics "$staging_run_id")
        fi
    fi

    # Verificar pod (se kubectl disponível)
    if [[ "$VERBOSE" == "true" ]]; then
        check_specialist_pod "$specialist"
    fi

    # Formatar output
    if [[ "$FORMAT" == "json" ]]; then
        cat << EOF
{
  "specialist": "$specialist",
  "model_name": "$model_name",
  "production": {
    "version": "$prod_version",
    "metrics": $prod_metrics,
    "run_id": "$prod_run_id",
    "last_updated": "$prod_timestamp"
  },
  "staging": {
    "version": "${staging_version:-N/A}",
    "metrics": $staging_metrics,
    "run_id": "$staging_run_id"
  }
}
EOF
    else
        # Formato table
        local precision recall f1
        precision=$(echo "$prod_metrics" | jq -r '.precision' 2>/dev/null || echo "N/A")
        recall=$(echo "$prod_metrics" | jq -r '.recall' 2>/dev/null || echo "N/A")
        f1=$(echo "$prod_metrics" | jq -r '.f1' 2>/dev/null || echo "N/A")

        # Cor baseada em métricas
        local color=$GREEN
        if [[ "$precision" != "N/A" ]] && (( $(echo "$precision < 0.75" | bc -l 2>/dev/null || echo "0") )); then
            color=$YELLOW
        fi
        if [[ "$f1" != "N/A" ]] && (( $(echo "$f1 < 0.72" | bc -l 2>/dev/null || echo "0") )); then
            color=$YELLOW
        fi
        if [[ "$prod_version" == "N/A" ]]; then
            color=$RED
        fi

        printf "${color}%-12s v%-4s  P=%-6s R=%-6s F1=%-6s %s${NC}\n" \
            "$specialist" "$prod_version" "$precision" "$recall" "$f1" "$prod_timestamp"

        if [[ "$VERBOSE" == "true" ]]; then
            echo -e "  ${BLUE}Run ID:${NC} $prod_run_id"
            if [[ -n "$staging_version" ]] && [[ "$staging_version" != "null" ]]; then
                echo -e "  ${YELLOW}Staging:${NC} v$staging_version"

                # Comparar métricas se ambas versões existem
                if [[ "$staging_metrics" != "N/A" ]] && [[ "$prod_metrics" != "N/A" ]]; then
                    local staging_f1 prod_f1_num
                    staging_f1=$(echo "$staging_metrics" | jq -r '.f1' 2>/dev/null || echo "0")
                    prod_f1_num=$(echo "$prod_metrics" | jq -r '.f1' 2>/dev/null || echo "0")

                    if [[ "$staging_f1" != "N/A" ]] && [[ "$prod_f1_num" != "N/A" ]]; then
                        local delta
                        delta=$(echo "scale=4; ($staging_f1 - $prod_f1_num) / $prod_f1_num * 100" | bc -l 2>/dev/null || echo "0")

                        if (( $(echo "$delta > 5" | bc -l 2>/dev/null || echo "0") )); then
                            echo -e "  ${GREEN}✓ Recomendação: Promover Staging para Production (+${delta}% F1)${NC}"
                        fi
                    fi
                fi
            fi
            echo ""
        fi
    fi
}

# Main
main() {
    # Verificar MLflow
    if ! check_mlflow_health; then
        exit 2
    fi

    # Header para formato table
    if [[ "$FORMAT" == "table" ]]; then
        echo -e "${BLUE}=== Status de Modelos ML - MLflow ===${NC}"
        echo -e "${BLUE}MLflow URI:${NC} $MLFLOW_URI"
        echo ""
        printf "%-12s %-6s  %-40s %s\n" "Specialist" "Ver" "Metrics" "Last Updated"
        printf "%-12s %-6s  %-40s %s\n" "----------" "---" "-------" "------------"
    fi

    # Processar especialistas
    if [[ "$FORMAT" == "json" ]]; then
        echo "["
    fi

    if [[ -n "$SPECIALIST" ]]; then
        process_specialist "$SPECIALIST"
    else
        local first=true
        for specialist in "${SPECIALISTS[@]}"; do
            if [[ "$FORMAT" == "json" ]]; then
                if [[ "$first" == "true" ]]; then
                    first=false
                else
                    echo ","
                fi
            fi

            process_specialist "$specialist"
        done
    fi

    if [[ "$FORMAT" == "json" ]]; then
        echo "]"
    fi

    # Footer para formato table
    if [[ "$FORMAT" == "table" ]]; then
        echo ""
        if [[ $EXIT_CODE -eq 0 ]]; then
            echo -e "${GREEN}✓ Todos os modelos OK${NC}"
        else
            echo -e "${RED}⚠️  Alguns modelos requerem atenção${NC}"
        fi

        echo ""
        echo -e "${BLUE}Dicas:${NC}"
        echo -e "  • Verificar detalhes: $0 --specialist technical --verbose"
        echo -e "  • Acessar MLflow UI: kubectl port-forward -n mlflow svc/mlflow 5000:5000"
        echo -e "  • Validar modelos: ml_pipelines/training/validate_models_loaded.sh"
    fi

    exit $EXIT_CODE
}

main
