#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
source "${SCRIPT_DIR}/validation/common-validation-functions.sh"

# Configurações padrão
TARGET="all"
PHASE=""
COMPONENT=""
NAMESPACE=""
REPORT_FORMAT="console"  # console, json, html, all
REPORT_FILE=""
FIX_ISSUES=false
VERBOSE=false
QUICK_MODE=false
REQUESTED_REPORT_PATH=""
REQUESTED_HTML_REPORT_PATH=""

# Parse argumentos
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --target)
                TARGET="$2"
                shift 2
                ;;
            --phase)
                PHASE="$2"
                shift 2
                ;;
            --component)
                COMPONENT="$2"
                shift 2
                ;;
            --namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            --report)
                REPORT_FORMAT="$2"
                shift 2
                ;;
            --report-file)
                REPORT_FILE="$2"
                shift 2
                ;;
            --fix)
                FIX_ISSUES=true
                shift
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --quick)
                QUICK_MODE=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "Argumento desconhecido: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

show_help() {
    cat << EOF
Neural Hive-Mind - CLI de Validação Unificado

USAGE:
    $0 --target <TARGET> [OPTIONS]

TARGETS:
    infrastructure      Validar infraestrutura (Kafka, Redis, MongoDB, Neo4j, etc)
    services           Validar serviços (Gateway, Consensus, Memory Layer, etc)
    specialists        Validar specialists (health, models, inference)
    security           Validar segurança (Vault, SPIRE, mTLS, OPA)
    observability      Validar observabilidade (Prometheus, Grafana, Jaeger)
    performance        Validar performance (SLOs, benchmarks, thresholds)
    phase              Validar fase específica (1, 2, all)
    e2e                Validar fluxo end-to-end completo
    all                Validar tudo (padrão)

OPTIONS:
    --phase <1|2|all>           Validar fase específica
    --component <NAME>          Validar componente específico
    --namespace <NS>            Namespace Kubernetes
    --report <FORMAT>           Formato do relatório: console, json, html, all (padrão: console)
    --report-file <FILE>        Arquivo de saída do relatório
    --fix                       Tentar corrigir problemas automaticamente
    --verbose                   Modo verbose
    --quick                     Modo rápido (pula testes longos)
    -h, --help                  Mostrar esta ajuda

EXAMPLES:
    # Validar tudo
    $0 --target all

    # Validar specialists com relatório HTML
    $0 --target specialists --report html --report-file /tmp/specialists-report.html

    # Validar fase 2 com modo verbose
    $0 --target phase --phase 2 --verbose

    # Validar observabilidade em namespace específico
    $0 --target observability --namespace neural-monitoring

    # Validar componente específico
    $0 --target services --component gateway

    # Validação rápida de infraestrutura
    $0 --target infrastructure --quick

    # Validar e tentar corrigir problemas
    $0 --target all --fix

ENVIRONMENT VARIABLES:
    NAMESPACE           Namespace Kubernetes padrão
    REPORT_DIR          Diretório para relatórios (padrão: /tmp/neural-hive-validation-reports)
    VERBOSE             Modo verbose (true/false)
    QUICK_MODE          Modo rápido (true/false)

EOF
}

# Carregar módulos de validação
load_modules() {
    local modules_dir="${SCRIPT_DIR}/validation/modules"
    
    source "${modules_dir}/specialists.sh"
    source "${modules_dir}/infrastructure.sh"
    source "${modules_dir}/services.sh"
    source "${modules_dir}/security.sh"
    source "${modules_dir}/observability.sh"
    source "${modules_dir}/performance.sh"
    source "${modules_dir}/phase.sh"
    source "${modules_dir}/e2e.sh"
}

# Executar validação baseada no target
run_validation() {
    local target="$1"
    
    case "$target" in
        infrastructure)
            validate_infrastructure
            ;;
        services)
            validate_services
            ;;
        specialists)
            validate_specialists
            ;;
        security)
            validate_security
            ;;
        observability)
            validate_observability
            ;;
        performance)
            validate_performance
            ;;
        phase)
            validate_phase
            ;;
        e2e)
            validate_e2e
            ;;
        all)
            validate_all
            ;;
        *)
            log_error "Target inválido: $target"
            show_help
            exit 1
            ;;
    esac
}

# Validar tudo
validate_all() {
    log_info "Executando validação completa..."
    
    validate_infrastructure
    validate_services
    validate_specialists
    validate_security
    validate_observability
    validate_performance
}

# Gerar relatório final
generate_final_report() {
    generate_summary_report
    
    case "$REPORT_FORMAT" in
        json)
            export_json_report
            ;;
        html)
            export_html_report
            ;;
        all)
            export_json_report
            export_html_report
            ;;
        console)
            # Já foi gerado por generate_summary_report
            ;;
    esac
    
    if [[ -n "$REPORT_FILE" ]]; then
        cp "$REPORT_FILE" "$REPORT_FILE" 2>/dev/null || true
    fi
}

# Main
main() {
    parse_args "$@"
    
    log_info "Neural Hive-Mind - Validação Unificada"
    log_info "Target: $TARGET"
    [[ -n "$PHASE" ]] && log_info "Phase: $PHASE"
    [[ -n "$COMPONENT" ]] && log_info "Component: $COMPONENT"
    [[ -n "$NAMESPACE" ]] && log_info "Namespace: $NAMESPACE"
    
    # Configurar caminhos de relatório solicitados
    if [[ -n "$REPORT_FILE" ]]; then
        REQUESTED_REPORT_PATH="$REPORT_FILE"
        REPORT_FILE="$REQUESTED_REPORT_PATH"
        if [[ "$REPORT_FORMAT" == "html" || "$REPORT_FORMAT" == "all" ]]; then
            REQUESTED_HTML_REPORT_PATH="$REQUESTED_REPORT_PATH"
            HTML_REPORT_FILE="$REQUESTED_HTML_REPORT_PATH"
        fi
        if [[ "$REPORT_FORMAT" == "all" && "$REQUESTED_HTML_REPORT_PATH" == "$REQUESTED_REPORT_PATH" ]]; then
            REQUESTED_HTML_REPORT_PATH="${REQUESTED_REPORT_PATH%.*}.html"
            HTML_REPORT_FILE="$REQUESTED_HTML_REPORT_PATH"
        fi
    fi
    
    # Inicializar relatório
    init_report "Validação Neural Hive-Mind - Target: $TARGET"
    
    # Carregar módulos
    load_modules
    
    # Executar validação
    run_validation "$TARGET"
    
    # Gerar relatório final
    generate_final_report
    
    # Copiar para o caminho solicitado (se diferente do gerado)
    if [[ -n "$REQUESTED_REPORT_PATH" && -f "$REPORT_FILE" && "$REPORT_FILE" != "$REQUESTED_REPORT_PATH" ]]; then
        cp "$REPORT_FILE" "$REQUESTED_REPORT_PATH"
    fi
    if [[ -n "$REQUESTED_HTML_REPORT_PATH" && -f "$HTML_REPORT_FILE" && "$HTML_REPORT_FILE" != "$REQUESTED_HTML_REPORT_PATH" ]]; then
        cp "$HTML_REPORT_FILE" "$REQUESTED_HTML_REPORT_PATH"
    fi
    
    # Exit code baseado em falhas
    if [[ $FAILED_TESTS -gt 0 ]]; then
        exit 1
    else
        exit 0
    fi
}

main "$@"
