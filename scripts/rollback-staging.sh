#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Neural Hive Mind - Script de Rollback Automatizado
# =============================================================================
#
# Uso:
#   ./scripts/rollback-staging.sh [opcoes]
#
# Opcoes:
#   -e, --env ENV           Ambiente (staging|production, padrao: staging)
#   -s, --services LIST     Lista de servicos separados por virgula
#   -r, --revision REVISION Revisao Helm para rollback (padrao: anterior)
#   -y, --yes               Confirmar automaticamente prompts
#   -d, --dry-run           Simular rollback sem modificar o ambiente
#   -f, --force             Forcar rollback mesmo com health checks falhando
#   --skip-health-checks    Pular verificacoes de saude pos-rollback
#   -h, --help              Mostrar ajuda
#
# Exemplos:
#   ./scripts/rollback-staging.sh --env staging --services queen-mcp-server
#   ./scripts/rollback-staging.sh --env production --services queen-mcp-server,worker-mcp-server --revision 2
#   ./scripts/rollback-staging.sh --dry-run --services queen-mcp-server
#
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ROLLBACK_LOG_DIR="${PROJECT_ROOT}/logs/rollback"
ROLLBACK_LOG_FILE="${ROLLBACK_LOG_DIR}/rollback-$(date +%Y%m%d-%H%M%S).log"

# Cores para output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

# Configuracoes padrao
DEPLOY_ENV="${DEPLOY_ENV:-staging}"
ROLLBACK_SERVICES="${ROLLBACK_SERVICES:-}"
REVISION="${REVISION:-}"
AUTO_CONFIRM="${AUTO_CONFIRM:-false}"
DRY_RUN="${DRY_RUN:-false}"
FORCE_ROLLBACK="${FORCE_ROLLBACK:-false}"
SKIP_HEALTH_CHECKS="${SKIP_HEALTH_CHECKS:-false}"
HEALTH_CHECK_TIMEOUT="${HEALTH_CHECK_TIMEOUT:-300}"

# Lista completa de servicos
MCP_SERVICES=(
    "queen-mcp-server"
    "worker-mcp-server"
    "analyst-mcp-server"
    "architect-mcp-server"
    "guard-mcp-server"
    "code-forge-mcp-server"
    "healer-mcp-server"
    "execution-mcp-server"
    "scout-mcp-server"
)

CORE_SERVICES=(
    "queen-agent"
    "worker-agents"
    "analyst-agents"
    "scout-agents"
    "guard-agents"
    "consensus-engine"
    "orchestrator-dynamic"
)

# Variaveis de tracking
declare -a ROLLED_BACK_SERVICES=()
declare -a FAILED_SERVICES=()
declare -a SKIPPED_SERVICES=()
ROLLBACK_START_TIME=$(date +%s)

# =============================================================================
# Funcoes de Logging
# =============================================================================

log_timestamp() {
    date "+%Y-%m-%d %H:%M:%S"
}

log_info() {
    printf "%b[%s] [INFO] %s%b\n" "${BLUE}" "$(log_timestamp)" "$*" "${NC}" >&2
    printf "[%s] [INFO] %s\n" "$(log_timestamp)" "$*" >> "${ROLLBACK_LOG_FILE}"
}

log_success() {
    printf "%b[%s] \342\234\205 %s%b\n" "${GREEN}" "$(log_timestamp)" "$*" "${NC}" >&2
    printf "[%s] [SUCCESS] %s\n" "$(log_timestamp)" "$*" >> "${ROLLBACK_LOG_FILE}"
}

log_error() {
    printf "%b[%s] \342\235\214 %s%b\n" "${RED}" "$(log_timestamp)" "$*" "${NC}" >&2
    printf "[%s] [ERROR] %s\n" "$(log_timestamp)" "$*" >> "${ROLLBACK_LOG_FILE}"
}

log_warning() {
    printf "%b[%s] \342\234\205 %s%b\n" "${YELLOW}" "$(log_timestamp)" "$*" "${NC}" >&2
    printf "[%s] [WARNING] %s\n" "$(log_timestamp)" "$*" >> "${ROLLBACK_LOG_FILE}"
}

log_section() {
    printf "\n%b========== %s ==========%b\n" "${CYAN}" "$*" "${NC}" >&2
    printf "\n========== %s ==========\n" "$*" >> "${ROLLBACK_LOG_FILE}"
}

# =============================================================================
# Funcoes Utilitarias
# =============================================================================

show_help() {
    cat << EOF
${CYAN}Neural Hive Mind - Script de Rollback Automatizado${NC}

${YELLOW}Uso:${NC}
  $0 [opcoes]

${YELLOW}Opcoes:${NC}
  -e, --env ENV           Ambiente (staging|production, padrao: staging)
  -s, --services LIST     Lista de servicos separados por virgula
  -r, --revision REVISION Revisao Helm para rollback (padrao: anterior)
  -y, --yes               Confirmar automaticamente prompts
  -d, --dry-run           Simular rollback sem modificar o ambiente
  -f, --force             Forcar rollback mesmo com health checks falhando
  --skip-health-checks    Pular verificacoes de saude pos-rollback
  -h, --help              Mostrar esta ajuda

${YELLOW}Servicos disponiveis:${NC}
  MCP: queen-mcp-server, worker-mcp-server, analyst-mcp-server,
       architect-mcp-server, guard-mcp-server, code-forge-mcp-server,
       healer-mcp-server, execution-mcp-server, scout-mcp-server
  Core: queen-agent, worker-agents, analyst-agents, scout-agents,
        guard-agents, consensus-engine, orchestrator-dynamic

${YELLOW}Exemplos:${NC}
  # Rollback de servico MCP para versao anterior
  $0 --env staging --services queen-mcp-server

  # Rollback para revisao especifica
  $0 --env production --services queen-mcp-server --revision 2

  # Rollback de multiplos servicos
  $0 --services queen-mcp-server,worker-mcp-server --yes

  # Simular rollback (dry-run)
  $0 --dry-run --services queen-mcp-server

${RED}AVISO: Rollback em producao requer confirmacao explicita (use --yes para auto-confirmar)${NC}

EOF
}

confirm_prompt() {
    local message="$1"
    local response

    if [[ "${AUTO_CONFIRM}" == "true" ]]; then
        return 0
    fi

    while true; do
        printf "%b[CONFIRM] %s [y/N]: %b" "${YELLOW}" "${message}" "${NC}" >&2
        read -r response
        case "${response}" in
            [yY][eE][sS]|[yY])
                return 0
                ;;
            [nN][oO]|[nN]|"")
                return 1
                ;;
            *)
                printf "Por favor responda yes ou no.\n" >&2
                ;;
        esac
    done
}

create_log_dir() {
    mkdir -p "${ROLLBACK_LOG_DIR}"
}

check_prerequisites() {
    log_section "Verificando Pre-requisitos"

    local missing=0
    local required_commands=("kubectl" "helm")

    for cmd in "${required_commands[@]}"; do
        if ! command -v "${cmd}" >/dev/null 2>&1; then
            log_error "Comando obrigatorio nao encontrado: ${cmd}"
            missing=1
        else
            log_info "Comando encontrado: ${cmd}"
        fi
    done

    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_error "kubectl nao consegue conectar ao cluster Kubernetes"
        missing=1
    fi

    if [[ $missing -ne 0 ]]; then
        log_error "Pre-requisitos nao atendidos. Abortando."
        exit 1
    fi

    log_success "Todos os pre-requisitos verificados"
}

get_helm_release_info() {
    local service="$1"
    local namespace="${DEPLOY_ENV}"

    if ! helm status "${service}" -n "${namespace}" >/dev/null 2>&1; then
        log_warning "Release Helm ${service} nao encontrado em ${namespace}"
        return 1
    fi

    helm status "${service}" -n "${namespace}" -o json 2>/dev/null || echo "{}"
}

get_helm_revision_history() {
    local service="$1"
    local namespace="${DEPLOY_ENV}"

    log_info "Historico de revisoes para ${service}:"
    helm history "${service}" -n "${namespace}" -o table 2>/dev/null || true
}

# =============================================================================
# Funcoes de Rollback
# =============================================================================

rollback_single_service() {
    local service="$1"
    local target_revision="${2:-}"
    local namespace="${DEPLOY_ENV}"

    log_section "Rollback de ${service}"

    # Verificar se release existe
    local release_info
    release_info=$(get_helm_release_info "${service}")
    if [[ -z "${release_info}" ]]; then
        log_error "Release Helm ${service} nao encontrado"
        FAILED_SERVICES+=("${service} (release nao encontrado)")
        return 1
    fi

    # Mostrar historico se nenhuma revisao foi especificada
    if [[ -z "${target_revision}" ]]; then
        get_helm_revision_history "${service}"

        # Pegar a revisao anterior (penultima linha do history)
        local previous_revision
        previous_revision=$(helm history "${service}" -n "${namespace}" -o json | \
            jq -r '[-2].revision // empty' 2>/dev/null || echo "")

        if [[ -z "${previous_revision}" ]]; then
            log_error "Nao ha revisao anterior para fazer rollback"
            FAILED_SERVICES+=("${service} (sem revisao anterior)")
            return 1
        fi

        target_revision="${previous_revision}"
        log_info "Alvo de rollback: revisao ${target_revision}"
    fi

    # Confirmar rollback
    if ! confirm_prompt "Confirmar rollback de ${service} para revisao ${target_revision}?"; then
        log_warning "Rollback de ${service} cancelado pelo usuario"
        SKIPPED_SERVICES+=("${service}")
        return 0
    fi

    # Executar rollback
    local rollback_cmd="helm rollback ${service} ${target_revision} -n ${namespace}"

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY-RUN] Rollback: ${rollback_cmd}"
        ROLLED_BACK_SERVICES+=("${service} (dry-run)")
        return 0
    fi

    log_info "Executando rollback para revisao ${target_revision}..."
    if eval "${rollback_cmd}" >> "${ROLLBACK_LOG_FILE}" 2>&1; then
        log_success "Rollback executado: ${service} -> revisao ${target_revision}"

        # Aguardar pods ficarem prontos
        if [[ "${SKIP_HEALTH_CHECKS}" != "true" ]]; then
            wait_for_rollback_ready "${service}" "${namespace}" || \
                log_warning "Health check timeout apos rollback, mas rollback foi executado"
        fi

        ROLLED_BACK_SERVICES+=("${service}")
        return 0
    else
        log_error "Rollback falhou para ${service}"
        FAILED_SERVICES+=("${service}")
        return 1
    fi
}

wait_for_rollback_ready() {
    local service="$1"
    local namespace="${2:-${DEPLOY_ENV}}"
    local timeout="${HEALTH_CHECK_TIMEOUT}"
    local elapsed=0
    local interval=5

    log_info "Aguardando pods de ${service} ficarem prontos apos rollback..."

    while [[ ${elapsed} -lt ${timeout} ]]; do
        local ready_pods
        ready_pods=$(kubectl get pods -n "${namespace}" -l "app.kubernetes.io/name=${service}" \
            -o jsonpath='{.items[*].status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "")

        if [[ -n "${ready_pods}" && ! "${ready_pods}" =~ "False" ]]; then
            local pod_count
            pod_count=$(kubectl get pods -n "${namespace}" -l "app.kubernetes.io/name=${service}" \
                -o jsonpath='{.items}' | jq '. | length' 2>/dev/null || echo "0")

            if [[ "${pod_count}" -gt 0 ]]; then
                log_success "Pods de ${service} prontos apos rollback (${pod_count} pods)"
                return 0
            fi
        fi

        sleep "${interval}"
        elapsed=$((elapsed + interval))
    done

    if [[ "${FORCE_ROLLBACK}" != "true" ]]; then
        log_error "Timeout aguardando pods de ${service} apos rollback"
        return 1
    else
        log_warning "Timeout aguardando pods, mas force esta habilitado"
        return 0
    fi
}

# =============================================================================
# Funcoes de Rollback em Cascata
# =============================================================================

rollback_with_dependencies() {
    local service="$1"
    local target_revision="${2:-}"
    local namespace="${DEPLOY_ENV}"

    # Mapa de dependencias (servico -> seus dependentes)
    # O rollback deve ser feito na ordem inversa: dependentes primeiro
    declare -A dependencies=(
        ["queen-mcp-server"]="worker-mcp-server analyst-mcp-server architect-mcp-server"
        ["consensus-engine"]="orchestrator-dynamic"
        ["orchestrator-dynamic"]="worker-agents"
        ["worker-mcp-server"]="execution-mcp-server"
    )

    # Verificar se ha dependentes que tambem estao na lista de rollback
    local dependents
    dependents="${dependencies[$service]:-}"

    if [[ -n "${dependents}" ]]; then
        log_info "Verificando dependentes de ${service}: ${dependents}"

        IFS=',' read -ra requested_services <<< "${ROLLBACK_SERVICES}"
        for dependent in ${dependents}; do
            for requested in "${requested_services[@]}"; do
                requested=$(echo "${requested}" | xargs)
                if [[ "${dependent}" == "${requested}" ]]; then
                    log_warning "Dependente ${dependent} tambem sera rollbacked - ordem pode ser importante"
                fi
            done
        done
    fi

    rollback_single_service "${service}" "${target_revision}"
}

# =============================================================================
# Funcoes de Diagnostico
# =============================================================================

show_rollback_diagnostics() {
    local namespace="${DEPLOY_ENV}"

    log_section "Diagnosticos do Ambiente"

    echo "Releases Helm instalados:"
    helm list -n "${namespace}" 2>/dev/null || echo "  Nenhum release encontrado"

    echo ""
    echo "Pods com problemas:"
    kubectl get pods -n "${namespace}" -o json | \
        jq -r '.items[] | select(.status.phase != "Running") | "\(.metadata.name): \(.status.phase)"' 2>/dev/null || \
        kubectl get pods -n "${namespace}" | grep -v "Running\|Completed" || echo "  Todos os pods estao funcionando"

    echo ""
    echo "Eventos recentes:"
    kubectl get events -n "${namespace}" --sort-by='.lastTimestamp' | tail -20 || true
}

save_rollback_snapshot() {
    local namespace="${DEPLOY_ENV}"
    local snapshot_file="${ROLLBACK_LOG_DIR}/snapshot-${namespace}-$(date +%Y%m%d-%H%M%S).txt"

    log_info "Salvando snapshot do estado atual..."

    {
        echo "=== Rollback Snapshot - $(date) ==="
        echo ""
        echo "=== Helm Releases ==="
        helm list -n "${namespace}" -a
        echo ""
        echo "=== Pods ==="
        kubectl get pods -n "${namespace}" -o wide
        echo ""
        echo "=== Services ==="
        kubectl get svc -n "${namespace}"
        echo ""
        echo "=== Recent Events ==="
        kubectl get events -n "${namespace}" --sort-by='.lastTimestamp' | tail -50
    } > "${snapshot_file}" 2>/dev/null || true

    log_info "Snapshot salvo: ${snapshot_file}"
}

# =============================================================================
# Funcoes de Relatorio
# =============================================================================

show_rollback_summary() {
    log_section "Resumo do Rollback"

    echo "Ambiente: ${DEPLOY_ENV}"
    echo "Servicos: ${ROLLBACK_SERVICES}"
    echo "Dry Run: ${DRY_RUN}"
    echo "Force: ${FORCE_ROLLBACK}"
    echo ""
}

show_rollback_results() {
    local rollback_end_time
    rollback_end_time=$(date +%s)
    local duration=$((rollback_end_time - ROLLBACK_START_TIME))
    local duration_minutes=$((duration / 60))
    local duration_seconds=$((duration % 60))

    log_section "Resultados do Rollback"

    echo "Duracao total: ${duration_minutes}m ${duration_seconds}s"
    echo ""

    if [[ ${#ROLLED_BACK_SERVICES[@]} -gt 0 ]]; then
        printf "${GREEN}Servicos rollbackados com sucesso (${#ROLLED_BACK_SERVICES[@]}):${NC}\n"
        for service in "${ROLLED_BACK_SERVICES[@]}"; do
            echo "  - ${service}"
        done
        echo ""
    fi

    if [[ ${#FAILED_SERVICES[@]} -gt 0 ]]; then
        printf "${RED}Servicos com falha no rollback (${#FAILED_SERVICES[@]}):${NC}\n"
        for service in "${FAILED_SERVICES[@]}"; do
            echo "  - ${service}"
        done
        echo ""
    fi

    if [[ ${#SKIPPED_SERVICES[@]} -gt 0 ]]; then
        printf "${YELLOW}Servicos pulados (${#SKIPPED_SERVICES[@]}):${NC}\n"
        for service in "${SKIPPED_SERVICES[@]}"; do
            echo "  - ${service}"
        done
        echo ""
    fi

    # Log file location
    echo "Log detalhado: ${ROLLBACK_LOG_FILE}"
}

# =============================================================================
# Funcoes de Validacao
# =============================================================================

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -e|--env)
                DEPLOY_ENV="${2:-staging}"
                shift 2
                ;;
            -s|--services)
                ROLLBACK_SERVICES="${2:-}"
                shift 2
                ;;
            -r|--revision)
                REVISION="${2:-}"
                shift 2
                ;;
            -y|--yes)
                AUTO_CONFIRM="true"
                shift
                ;;
            -d|--dry-run)
                DRY_RUN="true"
                shift
                ;;
            -f|--force)
                FORCE_ROLLBACK="true"
                shift
                ;;
            --skip-health-checks)
                SKIP_HEALTH_CHECKS="true"
                shift
                ;;
            --timeout)
                HEALTH_CHECK_TIMEOUT="${2:-300}"
                shift 2
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "Opcao desconhecida: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

validate_arguments() {
    if [[ "${DEPLOY_ENV}" != "staging" && "${DEPLOY_ENV}" != "production" ]]; then
        log_error "Ambiente invalido: ${DEPLOY_ENV} (deve ser staging ou production)"
        exit 1
    fi

    if [[ -z "${ROLLBACK_SERVICES}" ]]; then
        log_warning "Nenhum servico especificado com --services"
        log_info "Use --help para ver a lista de servicos disponiveis"
        exit 0
    fi
}

# =============================================================================
# Main
# =============================================================================

main() {
    create_log_dir
    parse_arguments "$@"
    validate_arguments

    log_section "Neural Hive Mind - Rollback Automatizado"
    log_info "Ambiente: ${DEPLOY_ENV}"
    log_info "Log: ${ROLLBACK_LOG_FILE}"

    # Verificar pre-requisitos
    check_prerequisites

    # Salvar snapshot antes do rollback
    save_rollback_snapshot

    # Mostrar diagnosticos
    show_rollback_diagnostics

    # Mostrar resumo
    show_rollback_summary

    # Confirmar rollback (especialmente em producao)
    if [[ "${DEPLOY_ENV}" == "production" && "${AUTO_CONFIRM}" != "true" ]]; then
        printf "%b[WARNING] Rollback para PRODUCAO foi solicitado.%b\n" "${RED}" "${NC}" >&2
        if ! confirm_prompt "Confirmar rollback em PRODUCAO? Esta operacao ira reverter versoes em producao."; then
            log_warning "Rollback cancelado pelo usuario"
            exit 0
        fi
    elif [[ "${AUTO_CONFIRM}" != "true" ]]; then
        if ! confirm_prompt "Iniciar rollback de ${ROLLBACK_SERVICES} em ${DEPLOY_ENV}?"; then
            log_warning "Rollback cancelado pelo usuario"
            exit 0
        fi
    fi

    # Processar cada servico
    IFS=',' read -ra services <<< "${ROLLBACK_SERVICES}"
    for service in "${services[@]}"; do
        service=$(echo "${service}" | xargs) # trim whitespace
        rollback_with_dependencies "${service}" "${REVISION}" || true
    done

    # Mostrar resultados
    show_rollback_results

    # Diagnosticos pos-rollback se houve falhas
    if [[ ${#FAILED_SERVICES[@]} -gt 0 ]]; then
        log_warning "Houve falhas no rollback. Executando diagnosticos..."
        show_rollback_diagnostics
    fi

    # Retornar status baseado em falhas
    if [[ ${#FAILED_SERVICES[@]} -gt 0 ]]; then
        log_error "Rollback concluido com falhas"
        exit 1
    else
        log_success "Rollback concluido com sucesso"
        exit 0
    fi
}

# Executar main
main "$@"
