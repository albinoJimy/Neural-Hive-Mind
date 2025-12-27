#!/bin/bash
# validate.sh - Comando para validar modelos carregados
#
# Uso: ml.sh validate [OPCOES]
#
# Exemplos:
#   ml.sh validate --all
#   ml.sh validate --specialist technical --verbose

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ml_common.sh"
source "${SCRIPT_DIR}/../lib/mlflow_utils.sh"

# Opcoes padrao
SPECIALIST=""
ALL_SPECIALISTS=false
VERBOSE=false
CHECK_PODS=false
MODEL_NAME=""
MODEL_VERSION=""
MIN_PRECISION=""
MIN_RECALL=""
MIN_F1=""

# Funcao de ajuda
show_help() {
    cat << EOF
validate - Validar modelos carregados

Uso: ml.sh validate [OPCOES]

OPCOES:
    --specialist TYPE   Validar especialista especifico (technical|business|behavior|evolution|architecture)
    --all               Validar todos os 5 especialistas (padrao se nenhum especificado)
    --model-name NAME   Validar modelo especifico registrado no MLflow
    --model-version N   Versao do modelo (default: Production)
    --min-precision N   Threshold minimo de precision (override de PROMOTION_THRESHOLD_PRECISION)
    --min-recall N      Threshold minimo de recall (override de PROMOTION_THRESHOLD_RECALL)
    --min-f1 N          Threshold minimo de F1 (override de PROMOTION_THRESHOLD_F1)
    --verbose           Mostrar informacoes detalhadas
    --check-pods        Verificar modelos carregados nos pods Kubernetes
    -h, --help          Mostrar esta mensagem

EXEMPLOS:
    ml.sh validate --all
    ml.sh validate --specialist technical --verbose
    ml.sh validate --model-name my-model --model-version 3 --min-f1 0.8
    ml.sh validate --all --check-pods --verbose

O QUE E VALIDADO:
    - Modelo registrado no MLflow
    - Versao em Production existe
    - Metricas atendem thresholds minimos
    - (Opcional) Modelo carregado no pod Kubernetes

CODIGOS DE SAIDA:
    0   Sucesso - todos os modelos validados
    1   Falha - pelo menos um modelo com status FAIL
    2   Avisos - pelo menos um modelo com status WARN (sem FAIL)

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
        --model-name)
            MODEL_NAME="$2"
            shift 2
            ;;
        --model-version)
            MODEL_VERSION="$2"
            shift 2
            ;;
        --min-precision)
            MIN_PRECISION="$2"
            shift 2
            ;;
        --min-recall)
            MIN_RECALL="$2"
            shift 2
            ;;
        --min-f1)
            MIN_F1="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --check-pods)
            CHECK_PODS=true
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

# Validacoes de combinacao de parametros
if [[ -n "$MODEL_NAME" ]] && { [[ "$ALL_SPECIALISTS" == "true" ]] || [[ -n "$SPECIALIST" ]]; }; then
    log_error "Nao combine --model-name com --specialist/--all"
    exit 1
fi

# Default para --all se nenhum especificado e sem modelo direto
if [[ -z "$SPECIALIST" ]] && [[ "$ALL_SPECIALISTS" == "false" ]] && [[ -z "$MODEL_NAME" ]]; then
    ALL_SPECIALISTS=true
fi

if [[ -n "$SPECIALIST" ]]; then
    validate_specialist_type "$SPECIALIST" || exit 1
fi

THRESHOLD_PRECISION="${MIN_PRECISION:-${PROMOTION_THRESHOLD_PRECISION:-}}"
THRESHOLD_RECALL="${MIN_RECALL:-${PROMOTION_THRESHOLD_RECALL:-}}"
THRESHOLD_F1="${MIN_F1:-${PROMOTION_THRESHOLD_F1:-0.72}}"

# Checa metricas contra thresholds configurados
check_threshold() {
    local value="$1"
    local threshold="$2"
    local label="$3"
    local status_ref="$4"
    local issues_ref="$5"

    if [[ -z "$threshold" ]]; then
        return
    fi

    if [[ -z "$value" ]] || [[ "$value" == "null" ]] || [[ "$value" == "N/A" ]]; then
        return
    fi

    if (( $(echo "$value < $threshold" | bc -l 2>/dev/null || echo "1") )); then
        eval "$status_ref=\"WARN\""
        eval "$issues_ref+=(\"$label abaixo do threshold ($value < $threshold)\")"
    fi
}

# Funcao para validar um specialist
validate_specialist() {
    local specialist="$1"
    local model_name="${specialist}-evaluator"
    local status="OK"
    local issues=()

    if [[ "$VERBOSE" == "true" ]]; then
        log_info "Validando: $specialist"
    fi

    # Verificar se modelo existe no MLflow
    if ! mlflow_get_model_info "$model_name" > /dev/null 2>&1; then
        status="FAIL"
        issues+=("Modelo nao registrado no MLflow")
    else
        # Verificar versao em Production
        local prod_version
        if ! prod_version=$(mlflow_get_production_version "$model_name" 2>/dev/null); then
            status="WARN"
            issues+=("Nenhuma versao em Production")
        else
            # Verificar metricas
            local metrics
            if metrics=$(mlflow_get_version_metrics "$model_name" "$prod_version" 2>/dev/null); then
                local precision recall f1
                precision=$(echo "$metrics" | jq -r '.precision' 2>/dev/null || echo "N/A")
                recall=$(echo "$metrics" | jq -r '.recall' 2>/dev/null || echo "N/A")
                f1=$(echo "$metrics" | jq -r '.f1' 2>/dev/null || echo "N/A")

                check_threshold "$precision" "$THRESHOLD_PRECISION" "Precision" status issues
                check_threshold "$recall" "$THRESHOLD_RECALL" "Recall" status issues
                check_threshold "$f1" "$THRESHOLD_F1" "F1 Score" status issues
            fi
        fi
    fi

    # Verificar pod se solicitado
    if [[ "$CHECK_PODS" == "true" ]] && command -v kubectl &> /dev/null; then
        local namespace="${K8S_NAMESPACE:-neural-hive}"
        local pod_name
        pod_name=$(kubectl get pods -n "$namespace" -l "app=specialist-$specialist" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

        if [[ -z "$pod_name" ]]; then
            status="WARN"
            issues+=("Pod nao encontrado")
        else
            local pod_status
            pod_status=$(kubectl get pod "$pod_name" -n "$namespace" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")

            if [[ "$pod_status" != "Running" ]]; then
                status="WARN"
                issues+=("Pod nao esta Running ($pod_status)")
            else
                # Verificar endpoint /status
                local model_loaded
                model_loaded=$(kubectl exec -n "$namespace" "$pod_name" -- curl -sf http://localhost:8080/status 2>/dev/null | jq -r '.model_loaded' 2>/dev/null || echo "false")

                if [[ "$model_loaded" != "true" ]]; then
                    status="WARN"
                    issues+=("Modelo nao carregado no pod")
                fi
            fi
        fi
    fi

    # Output
    local color icon
    case "$status" in
        OK)   color="${GREEN:-}"; icon="OK" ;;
        WARN) color="${YELLOW:-}"; icon="WARN" ;;
        FAIL) color="${RED:-}"; icon="FAIL" ;;
    esac

    if [[ "$VERBOSE" == "true" ]]; then
        printf "%b[%s] %s%b\n" "$color" "$icon" "$specialist" "${NC:-}"
        if [[ ${#issues[@]} -gt 0 ]]; then
            for issue in "${issues[@]}"; do
                echo "    - $issue"
            done
        fi
        if [[ "$status" == "OK" ]]; then
            local prod_version metrics
            prod_version=$(mlflow_get_production_version "$model_name" 2>/dev/null || echo "N/A")
            if [[ "$prod_version" != "N/A" ]]; then
                metrics=$(mlflow_get_version_metrics "$model_name" "$prod_version" 2>/dev/null || echo "{}")
                local precision recall f1
                precision=$(echo "$metrics" | jq -r '.precision' 2>/dev/null || echo "N/A")
                recall=$(echo "$metrics" | jq -r '.recall' 2>/dev/null || echo "N/A")
                f1=$(echo "$metrics" | jq -r '.f1' 2>/dev/null || echo "N/A")
                echo "    Production: v$prod_version (P=$precision R=$recall F1=$f1)"
            fi
        fi
    else
        printf "%b%-12s [%s]%b" "$color" "$specialist" "$icon" "${NC:-}"
        if [[ ${#issues[@]} -gt 0 ]]; then
            echo " - ${issues[0]}"
        else
            echo ""
        fi
    fi

    [[ "$status" == "OK" ]] && return 0
    [[ "$status" == "WARN" ]] && return 1
    return 2
}

validate_model_by_name() {
    local model_name="$1"
    local version="$2"
    local status="OK"
    local issues=()
    local metrics="{}"

    if ! mlflow_get_model_info "$model_name" > /dev/null 2>&1; then
        status="FAIL"
        issues+=("Modelo nao registrado no MLflow")
    fi

    if [[ "$status" != "FAIL" ]] && [[ -z "$version" ]]; then
        if ! version=$(mlflow_get_production_version "$model_name" 2>/dev/null); then
            status="WARN"
            issues+=("Nenhuma versao em Production")
        fi
    fi

    if [[ "$status" != "FAIL" ]] && [[ -n "$version" ]]; then
        if metrics=$(mlflow_get_version_metrics "$model_name" "$version" 2>/dev/null); then
            local precision recall f1
            precision=$(echo "$metrics" | jq -r '.precision' 2>/dev/null || echo "N/A")
            recall=$(echo "$metrics" | jq -r '.recall' 2>/dev/null || echo "N/A")
            f1=$(echo "$metrics" | jq -r '.f1' 2>/dev/null || echo "N/A")

            check_threshold "$precision" "$THRESHOLD_PRECISION" "Precision" status issues
            check_threshold "$recall" "$THRESHOLD_RECALL" "Recall" status issues
            check_threshold "$f1" "$THRESHOLD_F1" "F1 Score" status issues
        else
            status="FAIL"
            issues+=("Metricas nao encontradas para versao $version")
        fi
    fi

    local color icon
    case "$status" in
        OK)   color="${GREEN:-}"; icon="OK" ;;
        WARN) color="${YELLOW:-}"; icon="WARN" ;;
        FAIL) color="${RED:-}"; icon="FAIL" ;;
    esac

    if [[ "$VERBOSE" == "true" ]]; then
        printf "%b[%s] %s v%s%b\n" "$color" "$icon" "$model_name" "${version:-N/A}" "${NC:-}"
        if [[ ${#issues[@]} -gt 0 ]]; then
            for issue in "${issues[@]}"; do
                echo "    - $issue"
            done
        fi
        local precision recall f1
        precision=$(echo "$metrics" | jq -r '.precision' 2>/dev/null || echo "N/A")
        recall=$(echo "$metrics" | jq -r '.recall' 2>/dev/null || echo "N/A")
        f1=$(echo "$metrics" | jq -r '.f1' 2>/dev/null || echo "N/A")
        echo "    Metrics: P=$precision R=$recall F1=$f1"
    else
        printf "%b%-20s [%s]%b" "$color" "$model_name" "$icon" "${NC:-}"
        if [[ ${#issues[@]} -gt 0 ]]; then
            echo " - ${issues[0]}"
        else
            echo ""
        fi
    fi

    [[ "$status" == "OK" ]] && return 0
    [[ "$status" == "WARN" ]] && return 1
    return 2
}

# Main
main() {
    log_phase "Neural Hive - Model Validation"

    # Verificar MLflow
    if ! check_mlflow_connection; then
        exit 1
    fi

    echo ""

    local ok=0 warn=0 fail=0

    if [[ -n "$MODEL_NAME" ]]; then
        local result=0
        validate_model_by_name "$MODEL_NAME" "$MODEL_VERSION" || result=$?
        case $result in
            0) ((ok++)) ;;
            1) ((warn++)) ;;
            *) ((fail++)) ;;
        esac
    else
        local specialists=()
        if [[ -n "$SPECIALIST" ]]; then
            specialists=("$SPECIALIST")
        else
            specialists=("technical" "business" "behavior" "evolution" "architecture")
        fi

        for spec in "${specialists[@]}"; do
            local result=0
            validate_specialist "$spec" || result=$?

            case $result in
                0) ((ok++)) ;;
                1) ((warn++)) ;;
                *) ((fail++)) ;;
            esac
        done
    fi

    echo ""
    log_section "Resumo"
    echo "  OK:   $ok"
    echo "  WARN: $warn"
    echo "  FAIL: $fail"

    if [[ $fail -gt 0 ]]; then
        log_error "Validacao falhou"
        exit 1
    elif [[ $warn -gt 0 ]]; then
        log_warning "Validacao concluida com avisos"
        exit 2
    else
        log_success "Todos os modelos validados com sucesso"
        exit 0
    fi
}

main
