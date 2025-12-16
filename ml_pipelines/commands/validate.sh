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

# Funcao de ajuda
show_help() {
    cat << EOF
validate - Validar modelos carregados

Uso: ml.sh validate [OPCOES]

OPCOES:
    --specialist TYPE   Validar especialista especifico (technical|business|behavior|evolution|architecture)
    --all               Validar todos os 5 especialistas (padrao se nenhum especificado)
    --verbose           Mostrar informacoes detalhadas
    --check-pods        Verificar modelos carregados nos pods Kubernetes
    -h, --help          Mostrar esta mensagem

EXEMPLOS:
    ml.sh validate --all
    ml.sh validate --specialist technical --verbose
    ml.sh validate --all --check-pods --verbose

O QUE E VALIDADO:
    - Modelo registrado no MLflow
    - Versao em Production existe
    - Metricas atendem thresholds minimos
    - (Opcional) Modelo carregado no pod Kubernetes

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

# Default para --all se nenhum especificado
if [[ -z "$SPECIALIST" ]] && [[ "$ALL_SPECIALISTS" == "false" ]]; then
    ALL_SPECIALISTS=true
fi

if [[ -n "$SPECIALIST" ]]; then
    validate_specialist_type "$SPECIALIST" || exit 1
fi

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
                local f1
                f1=$(echo "$metrics" | jq -r '.f1' 2>/dev/null)

                if [[ "$f1" != "N/A" ]] && [[ "$f1" != "null" ]]; then
                    local threshold_f1="${PROMOTION_THRESHOLD_F1:-0.72}"
                    if (( $(echo "$f1 < $threshold_f1" | bc -l 2>/dev/null || echo "1") )); then
                        status="WARN"
                        issues+=("F1 Score abaixo do threshold ($f1 < $threshold_f1)")
                    fi
                fi
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

# Main
main() {
    log_phase "Neural Hive - Model Validation"

    # Verificar MLflow
    if ! check_mlflow_connection; then
        exit 1
    fi

    echo ""

    local specialists=()
    if [[ -n "$SPECIALIST" ]]; then
        specialists=("$SPECIALIST")
    else
        specialists=("technical" "business" "behavior" "evolution" "architecture")
    fi

    local ok=0 warn=0 fail=0

    for spec in "${specialists[@]}"; do
        local result=0
        validate_specialist "$spec" || result=$?

        case $result in
            0) ((ok++)) ;;
            1) ((warn++)) ;;
            *) ((fail++)) ;;
        esac
    done

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
        exit 0
    else
        log_success "Todos os modelos validados com sucesso"
        exit 0
    fi
}

main
