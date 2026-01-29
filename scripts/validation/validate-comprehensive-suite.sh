#!/bin/bash
# Suite abrangente de validações para Neural Hive-Mind
# Orquestra execução coordenada de todas as validações com relatório consolidado
# Version: 1.0

set -euo pipefail

# Carregar funções comuns
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common-validation-functions.sh"

# Configurações da suite
SUITE_TIMEOUT=3600  # 1 hora total
PARALLEL_EXECUTION=true
FAIL_FAST=false
RETRY_FAILED=true
MAX_RETRIES=2

# Scripts de validação disponíveis
declare -A VALIDATION_SCRIPTS=(
    ["cluster-health"]="${SCRIPT_DIR}/validate-cluster-health.sh"
    ["mtls-connectivity"]="${SCRIPT_DIR}/test-mtls-connectivity.sh"
    ["autoscaler"]="${SCRIPT_DIR}/test-autoscaler.sh"
    ["ha-connectivity"]="${SCRIPT_DIR}/validate-ha-connectivity.sh"
    ["disaster-recovery"]="${SCRIPT_DIR}/test-disaster-recovery.sh"
    ["performance-benchmarks"]="${SCRIPT_DIR}/validate-performance-benchmarks.sh"
)

# Dependências entre validações (prerequisito -> [dependentes])
declare -A VALIDATION_DEPENDENCIES=(
    ["cluster-health"]=""
    ["mtls-connectivity"]="cluster-health"
    ["autoscaler"]="cluster-health"
    ["ha-connectivity"]="cluster-health,mtls-connectivity"
    ["disaster-recovery"]="cluster-health,ha-connectivity"
    ["performance-benchmarks"]="cluster-health,mtls-connectivity"
)

# Criticidade por validação
declare -A VALIDATION_CRITICALITY=(
    ["cluster-health"]="critical"
    ["mtls-connectivity"]="high"
    ["autoscaler"]="high"
    ["ha-connectivity"]="medium"
    ["disaster-recovery"]="medium"
    ["performance-benchmarks"]="low"
)

# Resultados das validações
declare -A VALIDATION_RESULTS=()
declare -A VALIDATION_EXECUTION_TIMES=()
declare -A VALIDATION_RETRY_COUNTS=()
declare -A VALIDATION_REPORTS=()

# ============================================================================
# GERENCIAMENTO DE DEPENDÊNCIAS E EXECUÇÃO
# ============================================================================

# Verificar se todas as dependências de uma validação foram executadas com sucesso
check_dependencies_satisfied() {
    local validation="$1"
    local dependencies="${VALIDATION_DEPENDENCIES[$validation]}"

    if [[ -z "$dependencies" ]]; then
        return 0  # Sem dependências
    fi

    IFS=',' read -ra deps <<< "$dependencies"
    for dep in "${deps[@]}"; do
        local dep_result="${VALIDATION_RESULTS[$dep]:-}"
        if [[ "$dep_result" != "PASS" && "$dep_result" != "WARNING" ]]; then
            log_debug "Dependência $dep para $validation não satisfeita (resultado: $dep_result)"
            return 1
        fi
    done

    return 0
}

# Executar validação individual
execute_single_validation() {
    local validation="$1"
    local script_path="${VALIDATION_SCRIPTS[$validation]}"
    local criticality="${VALIDATION_CRITICALITY[$validation]}"

    if [[ ! -f "$script_path" ]]; then
        log_warning "Script de validação não encontrado: $script_path"
        VALIDATION_RESULTS["$validation"]="SKIP"
        add_test_result "validation-$validation" "SKIP" "$criticality" \
            "Script não encontrado: $script_path" "Verificar se script existe"
        return 1
    fi

    log_info "Executando validação: $validation"

    local start_time=$(date +%s)
    local temp_output=$(mktemp)
    local validation_exit_code=0

    # Executar script de validação
    if timeout "$SUITE_TIMEOUT" bash "$script_path" > "$temp_output" 2>&1; then
        validation_exit_code=0
    else
        validation_exit_code=$?
    fi

    local end_time=$(date +%s)
    local execution_time=$((end_time - start_time))
    VALIDATION_EXECUTION_TIMES["$validation"]=$execution_time

    # Processar resultado
    if [[ $validation_exit_code -eq 0 ]]; then
        VALIDATION_RESULTS["$validation"]="PASS"
        log_success "Validação $validation concluída com sucesso (${execution_time}s)"
    elif [[ $validation_exit_code -eq 124 ]]; then  # timeout
        VALIDATION_RESULTS["$validation"]="TIMEOUT"
        log_error "Validação $validation expirou após ${execution_time}s"
    else
        VALIDATION_RESULTS["$validation"]="FAIL"
        log_error "Validação $validation falhou (exit code: $validation_exit_code, ${execution_time}s)"
    fi

    # Salvar output da validação
    VALIDATION_REPORTS["$validation"]="$temp_output"

    # Processar resultado para relatório da suite
    case "${VALIDATION_RESULTS[$validation]}" in
        "PASS")
            add_test_result "validation-$validation" "PASS" "$criticality" \
                "Validação executada com sucesso em ${execution_time}s" ""
            ;;
        "TIMEOUT")
            add_test_result "validation-$validation" "FAIL" "$criticality" \
                "Validação expirou após ${execution_time}s" "Investigar performance ou aumentar timeout"
            ;;
        "FAIL")
            add_test_result "validation-$validation" "FAIL" "$criticality" \
                "Validação falhou (exit code: $validation_exit_code)" "Revisar logs da validação"
            ;;
    esac

    return $validation_exit_code
}

# Executar validações com retry
execute_with_retry() {
    local validation="$1"
    local retry_count=0

    while [[ $retry_count -le $MAX_RETRIES ]]; do
        if execute_single_validation "$validation"; then
            VALIDATION_RETRY_COUNTS["$validation"]=$retry_count
            return 0
        fi

        retry_count=$((retry_count + 1))

        if [[ $retry_count -le $MAX_RETRIES ]]; then
            log_warning "Tentativa $retry_count para validação $validation falhou, tentando novamente..."
            sleep 10
        else
            log_error "Validação $validation falhou após $MAX_RETRIES tentativas"
            VALIDATION_RETRY_COUNTS["$validation"]=$retry_count
            return 1
        fi
    done
}

# ============================================================================
# EXECUÇÃO SEQUENCIAL
# ============================================================================

# Executar validações em ordem de dependência
execute_sequential_validations() {
    log_info "Executando validações sequenciais..."

    local execution_order=(
        "cluster-health"
        "mtls-connectivity"
        "autoscaler"
        "ha-connectivity"
        "disaster-recovery"
        "performance-benchmarks"
    )

    for validation in "${execution_order[@]}"; do
        # Verificar se script existe
        if [[ ! -v "VALIDATION_SCRIPTS[$validation]" ]]; then
            log_debug "Validação $validation não disponível, pulando..."
            continue
        fi

        # Verificar dependências
        if ! check_dependencies_satisfied "$validation"; then
            log_warning "Dependências não satisfeitas para $validation, pulando..."
            VALIDATION_RESULTS["$validation"]="SKIP"
            add_test_result "validation-$validation" "SKIP" "${VALIDATION_CRITICALITY[$validation]}" \
                "Dependências não satisfeitas" "Corrigir validações dependentes"
            continue
        fi

        # Executar validação
        if [[ "$RETRY_FAILED" == "true" ]]; then
            execute_with_retry "$validation"
        else
            execute_single_validation "$validation"
        fi

        # Verificar fail-fast
        if [[ "$FAIL_FAST" == "true" && "${VALIDATION_RESULTS[$validation]}" == "FAIL" ]]; then
            local criticality="${VALIDATION_CRITICALITY[$validation]}"
            if [[ "$criticality" == "critical" ]]; then
                log_error "Validação crítica $validation falhou, interrompendo suite (fail-fast)"
                break
            fi
        fi
    done
}

# ============================================================================
# EXECUÇÃO PARALELA
# ============================================================================

# Executar validações independentes em paralelo
execute_parallel_validations() {
    log_info "Executando validações em paralelo..."

    # Identificar validações que podem ser executadas em paralelo
    local independent_validations=()
    local dependent_validations=()

    for validation in "${!VALIDATION_SCRIPTS[@]}"; do
        local dependencies="${VALIDATION_DEPENDENCIES[$validation]}"
        if [[ -z "$dependencies" ]]; then
            independent_validations+=("$validation")
        else
            dependent_validations+=("$validation")
        fi
    done

    # Executar validações independentes em paralelo
    local pids=()

    for validation in "${independent_validations[@]}"; do
        (
            if [[ "$RETRY_FAILED" == "true" ]]; then
                execute_with_retry "$validation"
            else
                execute_single_validation "$validation"
            fi
        ) &
        pids+=($!)
        log_debug "Iniciada validação paralela: $validation (PID: ${pids[-1]})"
    done

    # Aguardar validações independentes
    for i in "${!pids[@]}"; do
        local pid=${pids[$i]}
        local validation=${independent_validations[$i]}

        if wait $pid; then
            log_debug "Validação paralela $validation concluída com sucesso"
        else
            log_debug "Validação paralela $validation falhou"
        fi
    done

    # Executar validações dependentes sequencialmente
    for validation in "${dependent_validations[@]}"; do
        if ! check_dependencies_satisfied "$validation"; then
            log_warning "Dependências não satisfeitas para $validation, pulando..."
            VALIDATION_RESULTS["$validation"]="SKIP"
            add_test_result "validation-$validation" "SKIP" "${VALIDATION_CRITICALITY[$validation]}" \
                "Dependências não satisfeitas" "Corrigir validações dependentes"
            continue
        fi

        if [[ "$RETRY_FAILED" == "true" ]]; then
            execute_with_retry "$validation"
        else
            execute_single_validation "$validation"
        fi

        # Verificar fail-fast
        if [[ "$FAIL_FAST" == "true" && "${VALIDATION_RESULTS[$validation]}" == "FAIL" ]]; then
            local criticality="${VALIDATION_CRITICALITY[$validation]}"
            if [[ "$criticality" == "critical" ]]; then
                log_error "Validação crítica $validation falhou, interrompendo suite (fail-fast)"
                break
            fi
        fi
    done
}

# ============================================================================
# ANÁLISE E RELATÓRIOS
# ============================================================================

# Analisar resultados da suite
analyze_suite_results() {
    log_info "Analisando resultados da suite..."

    local total_validations=0
    local passed_validations=0
    local failed_validations=0
    local skipped_validations=0
    local timeout_validations=0

    for validation in "${!VALIDATION_RESULTS[@]}"; do
        local result="${VALIDATION_RESULTS[$validation]}"
        total_validations=$((total_validations + 1))

        case "$result" in
            "PASS") passed_validations=$((passed_validations + 1)) ;;
            "FAIL") failed_validations=$((failed_validations + 1)) ;;
            "SKIP") skipped_validations=$((skipped_validations + 1)) ;;
            "TIMEOUT") timeout_validations=$((timeout_validations + 1)) ;;
        esac
    done

    # Calcular taxa de sucesso
    local success_rate=0
    if [[ $total_validations -gt 0 ]]; then
        success_rate=$((passed_validations * 100 / total_validations))
    fi

    # Determinar status geral da suite
    local suite_status="PASS"
    if [[ $failed_validations -gt 0 || $timeout_validations -gt 0 ]]; then
        # Verificar se há falhas críticas
        local critical_failures=0
        for validation in "${!VALIDATION_RESULTS[@]}"; do
            local result="${VALIDATION_RESULTS[$validation]}"
            local criticality="${VALIDATION_CRITICALITY[$validation]}"
            if [[ "$result" == "FAIL" || "$result" == "TIMEOUT" ]] && [[ "$criticality" == "critical" ]]; then
                critical_failures=$((critical_failures + 1))
            fi
        done

        if [[ $critical_failures -gt 0 ]]; then
            suite_status="FAIL"
        else
            suite_status="WARNING"
        fi
    fi

    # Adicionar resultado da suite
    add_test_result "comprehensive-validation-suite" "$suite_status" "critical" \
        "Suite executada: $passed_validations/$total_validations passou ($success_rate%), $failed_validations falharam, $skipped_validations puladas" \
        "$(generate_suite_recommendations)"

    # Log do resumo
    log_info "Resultados da suite:"
    log_info "  Total: $total_validations validações"
    log_info "  Passou: $passed_validations ($success_rate%)"
    log_info "  Falhou: $failed_validations"
    log_info "  Timeout: $timeout_validations"
    log_info "  Puladas: $skipped_validations"
    log_info "  Status geral: $suite_status"
}

# Gerar recomendações específicas da suite
generate_suite_recommendations() {
    local recommendations=()

    # Analisar padrões de falha
    local network_failures=0
    local resource_failures=0
    local config_failures=0

    for validation in "${!VALIDATION_RESULTS[@]}"; do
        local result="${VALIDATION_RESULTS[$validation]}"
        if [[ "$result" == "FAIL" ]]; then
            case "$validation" in
                "mtls-connectivity"|"ha-connectivity")
                    network_failures=$((network_failures + 1))
                    ;;
                "autoscaler"|"cluster-health")
                    resource_failures=$((resource_failures + 1))
                    ;;
                *)
                    config_failures=$((config_failures + 1))
                    ;;
            esac
        fi
    done

    if [[ $network_failures -gt 1 ]]; then
        recommendations+=("Múltiplas falhas de rede detectadas - verificar configuração do Istio e políticas de rede")
    fi

    if [[ $resource_failures -gt 0 ]]; then
        recommendations+=("Problemas de recursos detectados - verificar capacidade do cluster e configuração do autoscaler")
    fi

    if [[ $config_failures -gt 0 ]]; then
        recommendations+=("Problemas de configuração detectados - revisar deployments e políticas")
    fi

    printf '%s; ' "${recommendations[@]}"
}

# Gerar relatório consolidado da suite
generate_consolidated_report() {
    log_info "Gerando relatório consolidado da suite..."

    local suite_report_file="${REPORT_DIR}/comprehensive-suite-${REPORT_TIMESTAMP}.json"
    local total_execution_time=$(measure_execution_time $SUITE_START_TIME)

    # Criar estrutura do relatório consolidado
    cat > "$suite_report_file" <<EOF
{
  "suite_metadata": {
    "script_name": "validate-comprehensive-suite",
    "version": "1.0",
    "execution_mode": "$(if [[ "$PARALLEL_EXECUTION" == "true" ]]; then echo "parallel"; else echo "sequential"; fi)",
    "start_time": $SUITE_START_TIME,
    "total_execution_time": $total_execution_time,
    "timestamp": "$(date -Iseconds)",
    "cluster_context": "$(kubectl config current-context 2>/dev/null || echo 'unknown')"
  },
  "validation_results": {
EOF

    # Adicionar resultados de cada validação
    local first=true
    for validation in "${!VALIDATION_RESULTS[@]}"; do
        if [[ "$first" == "false" ]]; then
            echo "," >> "$suite_report_file"
        fi
        first=false

        local result="${VALIDATION_RESULTS[$validation]}"
        local execution_time="${VALIDATION_EXECUTION_TIMES[$validation]:-0}"
        local retry_count="${VALIDATION_RETRY_COUNTS[$validation]:-0}"
        local criticality="${VALIDATION_CRITICALITY[$validation]}"
        local report_file="${VALIDATION_REPORTS[$validation]:-}"

        cat >> "$suite_report_file" <<EOF
    "$validation": {
      "result": "$result",
      "criticality": "$criticality",
      "execution_time": $execution_time,
      "retry_count": $retry_count,
      "report_file": "$report_file"
    }
EOF
    done

    cat >> "$suite_report_file" <<EOF
  },
  "suite_summary": {
    "total_validations": ${#VALIDATION_RESULTS[@]},
    "success_rate": $(( ${#VALIDATION_RESULTS[@]} > 0 ? $(count_passed_validations) * 100 / ${#VALIDATION_RESULTS[@]} : 0 )),
    "critical_failures": $(count_critical_failures),
    "recommendations": [$(generate_suite_recommendations | sed 's/; /", "/g' | sed 's/; $//' | sed 's/^/"/;s/$/"/')]
  }
}
EOF

    echo "$suite_report_file"
}

# Funções auxiliares para contagem
count_passed_validations() {
    local count=0
    for result in "${VALIDATION_RESULTS[@]}"; do
        if [[ "$result" == "PASS" ]]; then
            count=$((count + 1))
        fi
    done
    echo $count
}

count_critical_failures() {
    local count=0
    for validation in "${!VALIDATION_RESULTS[@]}"; do
        local result="${VALIDATION_RESULTS[$validation]}"
        local criticality="${VALIDATION_CRITICALITY[$validation]}"
        if [[ "$result" == "FAIL" && "$criticality" == "critical" ]]; then
            count=$((count + 1))
        fi
    done
    echo $count
}

# Gerar dashboard HTML consolidado
generate_consolidated_html_dashboard() {
    local html_file="${REPORT_DIR}/comprehensive-suite-dashboard-${REPORT_TIMESTAMP}.html"

    cat > "$html_file" <<EOF
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard de Validação Neural Hive-Mind</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { text-align: center; background: white; padding: 30px; border-radius: 8px; margin-bottom: 30px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .summary-card { background: white; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .summary-card h3 { margin: 0 0 10px 0; color: #666; }
        .summary-card .value { font-size: 2em; font-weight: bold; margin: 10px 0; }
        .validations-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; }
        .validation-card { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .validation-header { display: flex; justify-content: between; align-items: center; margin-bottom: 15px; }
        .validation-title { font-size: 1.2em; font-weight: bold; margin: 0; }
        .status-badge { padding: 4px 12px; border-radius: 20px; font-size: 0.8em; font-weight: bold; text-transform: uppercase; }
        .status-pass { background: #d4edda; color: #155724; }
        .status-fail { background: #f8d7da; color: #721c24; }
        .status-skip { background: #fff3cd; color: #856404; }
        .status-timeout { background: #f5c6cb; color: #721c24; }
        .criticality { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.7em; color: white; margin-left: 10px; }
        .crit-critical { background: #dc3545; }
        .crit-high { background: #fd7e14; }
        .crit-medium { background: #ffc107; color: #000; }
        .crit-low { background: #6c757d; }
        .execution-time { color: #666; font-size: 0.9em; }
        .retry-count { color: #666; font-size: 0.8em; }
        .progress-bar { width: 100%; height: 20px; background: #e9ecef; border-radius: 10px; overflow: hidden; margin: 20px 0; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #28a745, #20c997); transition: width 0.3s ease; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Dashboard de Validação Neural Hive-Mind</h1>
            <p>Suite Abrangente de Validações</p>
            <p><strong>Executado em:</strong> $(date)</p>
            <p><strong>Cluster:</strong> $(kubectl config current-context 2>/dev/null || echo 'unknown')</p>
        </div>

        <div class="summary-grid">
            <div class="summary-card">
                <h3>Total de Validações</h3>
                <div class="value">${#VALIDATION_RESULTS[@]}</div>
            </div>
            <div class="summary-card">
                <h3>Taxa de Sucesso</h3>
                <div class="value" style="color: #28a745;">$(( ${#VALIDATION_RESULTS[@]} > 0 ? $(count_passed_validations) * 100 / ${#VALIDATION_RESULTS[@]} : 0 ))%</div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: $(( ${#VALIDATION_RESULTS[@]} > 0 ? $(count_passed_validations) * 100 / ${#VALIDATION_RESULTS[@]} : 0 ))%;"></div>
                </div>
            </div>
            <div class="summary-card">
                <h3>Validações Aprovadas</h3>
                <div class="value" style="color: #28a745;">$(count_passed_validations)</div>
            </div>
            <div class="summary-card">
                <h3>Falhas Críticas</h3>
                <div class="value" style="color: #dc3545;">$(count_critical_failures)</div>
            </div>
        </div>

        <div class="validations-grid">
EOF

    # Adicionar cards para cada validação
    for validation in "${!VALIDATION_RESULTS[@]}"; do
        local result="${VALIDATION_RESULTS[$validation]}"
        local execution_time="${VALIDATION_EXECUTION_TIMES[$validation]:-0}"
        local retry_count="${VALIDATION_RETRY_COUNTS[$validation]:-0}"
        local criticality="${VALIDATION_CRITICALITY[$validation]}"

        local status_class=""
        case "$result" in
            "PASS") status_class="status-pass" ;;
            "FAIL") status_class="status-fail" ;;
            "SKIP") status_class="status-skip" ;;
            "TIMEOUT") status_class="status-timeout" ;;
        esac

        cat >> "$html_file" <<EOF
            <div class="validation-card">
                <div class="validation-header">
                    <h3 class="validation-title">$validation</h3>
                    <span class="status-badge $status_class">$result</span>
                    <span class="criticality crit-$criticality">$criticality</span>
                </div>
                <div class="execution-time">Tempo de execução: ${execution_time}s</div>
EOF

        if [[ $retry_count -gt 0 ]]; then
            cat >> "$html_file" <<EOF
                <div class="retry-count">Tentativas: $retry_count</div>
EOF
        fi

        cat >> "$html_file" <<EOF
            </div>
EOF
    done

    cat >> "$html_file" <<EOF
        </div>
    </div>
</body>
</html>
EOF

    echo "$html_file"
}

# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

main() {
    # Configurar variáveis globais
    SUITE_START_TIME=$(date +%s)

    # Processar argumentos
    while [[ $# -gt 0 ]]; do
        case $1 in
            --sequential)
                PARALLEL_EXECUTION=false
                shift
                ;;
            --fail-fast)
                FAIL_FAST=true
                shift
                ;;
            --no-retry)
                RETRY_FAILED=false
                shift
                ;;
            --timeout)
                SUITE_TIMEOUT="$2"
                shift 2
                ;;
            *)
                log_warning "Argumento desconhecido: $1"
                shift
                ;;
        esac
    done

    init_report "Suite abrangente de validações Neural Hive-Mind"

    log_info "Iniciando suite abrangente de validações..."
    log_info "Modo de execução: $(if [[ "$PARALLEL_EXECUTION" == "true" ]]; then echo "paralelo"; else echo "sequencial"; fi)"
    log_info "Fail-fast: $FAIL_FAST"
    log_info "Retry falhas: $RETRY_FAILED"
    log_info "Timeout total: ${SUITE_TIMEOUT}s"

    # Verificar pré-requisitos
    if ! check_prerequisites; then
        add_test_result "suite-prerequisites" "FAIL" "critical" "Pré-requisitos não atendidos" "Instalar ferramentas necessárias"
        generate_summary_report
        exit 1
    fi

    add_test_result "suite-prerequisites" "PASS" "high" "Todos os pré-requisitos atendidos" ""

    # Executar validações
    if [[ "$PARALLEL_EXECUTION" == "true" ]]; then
        execute_parallel_validations
    else
        execute_sequential_validations
    fi

    # Analisar resultados
    analyze_suite_results

    # Gerar relatórios
    generate_summary_report
    local consolidated_report=$(generate_consolidated_report)
    local html_dashboard=$(generate_consolidated_html_dashboard)
    local json_report=$(export_json_report)
    local html_report=$(export_html_report)

    # Limpar arquivos temporários
    for temp_file in "${VALIDATION_REPORTS[@]}"; do
        [[ -f "$temp_file" ]] && rm -f "$temp_file"
    done

    log_success "======================================================"
    log_success "Suite abrangente de validações concluída!"
    log_info "Tempo total de execução: $(measure_execution_time $SUITE_START_TIME)s"
    log_info "Relatórios gerados:"
    log_info "  - Relatório JSON: $json_report"
    log_info "  - Relatório HTML: $html_report"
    log_info "  - Relatório consolidado: $consolidated_report"
    log_info "  - Dashboard HTML: $html_dashboard"
    log_success "======================================================"

    # Exit code baseado nos resultados
    local critical_failures=$(count_critical_failures)
    if [[ $critical_failures -gt 0 ]]; then
        exit 1
    else
        exit 0
    fi
}

main "$@"