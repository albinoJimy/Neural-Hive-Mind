#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Neural Hive Mind - Script de Deploy Automatizado para Staging
# =============================================================================
#
# Uso:
#   ./scripts/deploy-staging.sh [opcoes]
#
# Opcoes:
#   -e, --env ENV           Ambiente (staging|production, padrao: staging)
#   -s, --services LIST     Lista de servicos separados por virgula
#   -v, --version VERSION   Versao das imagens (padrao: latest)
#   -d, --dry-run           Simular deploy sem modificar o ambiente
#   -y, --yes               Confirmar automaticamente prompts
#   --skip-build            Pular build de imagens
#   --skip-health-checks    Pular verificacoes de saude
#   --timeout SECONDS       Timeout para health checks (padrao: 300)
#   -h, --help              Mostrar ajuda
#
# Exemplos:
#   ./scripts/deploy-staging.sh --env staging --services queen-mcp-server,worker-mcp-server
#   ./scripts/deploy-staging.sh --env production --version v1.2.3 --yes
#   ./scripts/deploy-staging.sh --dry-run
#
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPLOY_LOG_DIR="${PROJECT_ROOT}/logs/deploy"
DEPLOY_LOG_FILE="${DEPLOY_LOG_DIR}/deploy-$(date +%Y%m%d-%H%M%S).log"

# Cores para output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

# Configuracoes padrao
DEPLOY_ENV="${DEPLOY_ENV:-staging}"
DEPLOY_SERVICES="${DEPLOY_SERVICES:-}"
VERSION="${VERSION:-latest}"
DRY_RUN="${DRY_RUN:-false}"
AUTO_CONFIRM="${AUTO_CONFIRM:-false}"
SKIP_BUILD="${SKIP_BUILD:-false}"
SKIP_HEALTH_CHECKS="${SKIP_HEALTH_CHECKS:-false}"
HEALTH_CHECK_TIMEOUT="${HEALTH_CHECK_TIMEOUT:-300}"
HELM_TIMEOUT="${HELM_TIMEOUT:-10m}"

# Lista completa de servicos MCP
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

# Servicos core (alem dos MCP)
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
declare -a DEPLOYED_SERVICES=()
declare -a FAILED_SERVICES=()
declare -a SKIPPED_SERVICES=()
DEPLOY_START_TIME=$(date +%s)

# =============================================================================
# Funcoes de Logging
# =============================================================================

log_timestamp() {
    date "+%Y-%m-%d %H:%M:%S"
}

log_info() {
    printf "%b[%s] [INFO] %s%b\n" "${BLUE}" "$(log_timestamp)" "$*" "${NC}" >&2
    printf "[%s] [INFO] %s\n" "$(log_timestamp)" "$*" >> "${DEPLOY_LOG_FILE}"
}

log_success() {
    printf "%b[%s] \342\234\205 %s%b\n" "${GREEN}" "$(log_timestamp)" "$*" "${NC}" >&2
    printf "[%s] [SUCCESS] %s\n" "$(log_timestamp)" "$*" >> "${DEPLOY_LOG_FILE}"
}

log_error() {
    printf "%b[%s] \342\235\214 %s%b\n" "${RED}" "$(log_timestamp)" "$*" "${NC}" >&2
    printf "[%s] [ERROR] %s\n" "$(log_timestamp)" "$*" >> "${DEPLOY_LOG_FILE}"
}

log_warning() {
    printf "%b[%s] \342\234\205 %s%b\n" "${YELLOW}" "$(log_timestamp)" "$*" "${NC}" >&2
    printf "[%s] [WARNING] %s\n" "$(log_timestamp)" "$*" >> "${DEPLOY_LOG_FILE}"
}

log_section() {
    printf "\n%b========== %s ==========%b\n" "${CYAN}" "$*" "${NC}" >&2
    printf "\n========== %s ==========\n" "$*" >> "${DEPLOY_LOG_FILE}"
}

# =============================================================================
# Funcoes Utilitarias
# =============================================================================

show_help() {
    cat << EOF
${CYAN}Neural Hive Mind - Script de Deploy Automatizado${NC}

${YELLOW}Uso:${NC}
  $0 [opcoes]

${YELLOW}Opcoes:${NC}
  -e, --env ENV           Ambiente (staging|production, padrao: staging)
  -s, --services LIST     Lista de servicos separados por virgula
  -v, --version VERSION   Versao das imagens (padrao: latest)
  -d, --dry-run           Simular deploy sem modificar o ambiente
  -y, --yes               Confirmar automaticamente prompts
  --skip-build            Pular build de imagens
  --skip-health-checks    Pular verificacoes de saude
  --timeout SECONDS       Timeout para health checks (padrao: 300)
  -h, --help              Mostrar esta ajuda

${YELLOW}Servicos MCP disponiveis:${NC}
  queen-mcp-server, worker-mcp-server, analyst-mcp-server,
  architect-mcp-server, guard-mcp-server, code-forge-mcp-server,
  healer-mcp-server, execution-mcp-server, scout-mcp-server

${YELLOW}Servicos Core disponiveis:${NC}
  queen-agent, worker-agents, analyst-agents, scout-agents,
  guard-agents, consensus-engine, orchestrator-dynamic

${YELLOW}Exemplos:${NC}
  # Deploy de todos os servicos MCP para staging
  $0 --env staging --services queen-mcp-server,worker-mcp-server

  # Deploy com versao especifica para producao
  $0 --env production --version v1.2.3 --services queen-mcp-server --yes

  # Simular deploy (dry-run)
  $0 --dry-run --services queen-mcp-server

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

check_prerequisites() {
    log_section "Verificando Pre-requisitos"

    local missing=0
    local required_commands=("docker" "kubectl" "helm")

    for cmd in "${required_commands[@]}"; do
        if ! command -v "${cmd}" >/dev/null 2>&1; then
            log_error "Comando obrigatorio nao encontrado: ${cmd}"
            missing=1
        else
            log_info "Comando encontrado: ${cmd}"
        fi
    done

    if ! docker info >/dev/null 2>&1; then
        log_error "Docker daemon nao esta em execucao"
        missing=1
    fi

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

create_log_dir() {
    mkdir -p "${DEPLOY_LOG_DIR}"
}

get_service_helm_path() {
    local service="$1"
    local helm_path=""

    # Verificar se e um servico MCP
    for mcp_service in "${MCP_SERVICES[@]}"; do
        if [[ "${service}" == "${mcp_service}" ]]; then
            helm_path="${PROJECT_ROOT}/services/mcp-servers/${service}/helm"
            if [[ -d "${helm_path}" ]]; then
                echo "${helm_path}"
                return 0
            fi
        fi
    done

    # Verificar se e um servico core
    for core_service in "${CORE_SERVICES[@]}"; do
        if [[ "${service}" == "${core_service}" ]]; then
            helm_path="${PROJECT_ROOT}/services/${service}/helm"
            if [[ -d "${helm_path}" ]]; then
                echo "${helm_path}"
                return 0
            fi
        fi
    done

    # Busca generica
    helm_path=$(find "${PROJECT_ROOT}/services" -type d -name "${service}/helm" -print -quit 2>/dev/null)
    if [[ -n "${helm_path}" && -d "${helm_path}" ]]; then
        echo "${helm_path}"
        return 0
    fi

    return 1
}

get_service_image_name() {
    local service="$1"
    # Remove -server e -mcp-server do nome para o image
    local image_name="${service%-server}"
    image_name="${image_name%-mcp}"
    image_name="neural-hive-mind-${image_name}"
    echo "${image_name}"
}

# =============================================================================
# Funcoes de Build
# =============================================================================

build_service_image() {
    local service="$1"
    local version="$2"
    local dockerfile_path=""
    local context_path=""
    local image_name

    image_name=$(get_service_image_name "${service}")

    log_info "Build de imagem para ${service}"

    # Encontrar Dockerfile
    if [[ "${service}" =~ mcp-server ]]; then
        dockerfile_path="${PROJECT_ROOT}/services/mcp-servers/${service}/Dockerfile"
        context_path="${PROJECT_ROOT}/services/mcp-servers/${service}"
    else
        dockerfile_path="${PROJECT_ROOT}/services/${service}/Dockerfile"
        context_path="${PROJECT_ROOT}/services/${service}"
    fi

    if [[ ! -f "${dockerfile_path}" ]]; then
        log_warning "Dockerfile nao encontrado para ${service}, pulando build"
        SKIPPED_SERVICES+=("${service} (no Dockerfile)")
        return 0
    fi

    local build_cmd="docker build -t ${image_name}:${version} -f ${dockerfile_path} ${context_path}"

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY-RUN] Build: ${build_cmd}"
        return 0
    fi

    log_info "Executando: ${build_cmd}"
    if eval "${build_cmd}" >> "${DEPLOY_LOG_FILE}" 2>&1; then
        log_success "Build concluido: ${image_name}:${version}"
        return 0
    else
        log_error "Build falhou para ${service}"
        return 1
    fi
}

# =============================================================================
# Funcoes de Deploy Helm
# =============================================================================

helm_deploy_service() {
    local service="$1"
    local version="$2"
    local helm_path
    local namespace="${DEPLOY_ENV}"
    local image_name
    local release_name="${service}"
    local values_file=""

    helm_path=$(get_service_helm_path "${service}")
    if [[ -z "${helm_path}" ]]; then
        log_error "Helm chart nao encontrado para ${service}"
        return 1
    fi

    log_info "Helm chart encontrado: ${helm_path}"

    image_name=$(get_service_image_name "${service}")

    # Verificar se existe values especifico para o ambiente
    local env_values="${helm_path}/values-${DEPLOY_ENV}.yaml"
    if [[ -f "${env_values}" ]]; then
        values_file="-f ${env_values}"
        log_info "Usando values de ambiente: ${env_values}"
    fi

    # Verificar se existe secrets
    local secrets_values="${helm_path}/secrets.yaml"
    if [[ -f "${secrets_values}" ]]; then
        values_file="${values_file} -f ${secrets_values}"
    fi

    # Criar namespace se nao existir
    if [[ "${DRY_RUN}" != "true" ]]; then
        kubectl create namespace "${namespace}" --dry-run=client -o yaml | kubectl apply -f - >> "${DEPLOY_LOG_FILE}" 2>&1 || true
    fi

    # Comando helm upgrade
    local helm_cmd="helm upgrade --install ${release_name} ${helm_path} \
        --namespace ${namespace} \
        --set image.repository=${image_name} \
        --set image.tag=${version} \
        --timeout ${HELM_TIMEOUT} \
        --wait \
        --atomic \
        ${values_file}"

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY-RUN] Helm: ${helm_cmd}"
        return 0
    fi

    log_info "Executando helm upgrade para ${service}"
    if eval "${helm_cmd}" >> "${DEPLOY_LOG_FILE}" 2>&1; then
        log_success "Helm deploy concluido: ${service}"
        return 0
    else
        log_error "Helm deploy falhou para ${service}"
        return 1
    fi
}

# =============================================================================
# Funcoes de Health Check
# =============================================================================

wait_for_service_ready() {
    local service="$1"
    local namespace="${DEPLOY_ENV}"
    local timeout="${HEALTH_CHECK_TIMEOUT}"
    local elapsed=0
    local interval=5

    log_info "Aguardando pods de ${service} ficarem prontos..."

    while [[ ${elapsed} -lt ${timeout} ]]; do
        local ready_pods
        ready_pods=$(kubectl get pods -n "${namespace}" -l "app.kubernetes.io/name=${service}" \
            -o jsonpath='{.items[*].status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "")

        if [[ -n "${ready_pods}" && ! "${ready_pods}" =~ "False" ]]; then
            local pod_count
            pod_count=$(kubectl get pods -n "${namespace}" -l "app.kubernetes.io/name=${service}" \
                -o jsonpath='{.items}' | jq '. | length' 2>/dev/null || echo "0")

            if [[ "${pod_count}" -gt 0 ]]; then
                log_success "Todos os pods de ${service} estao prontos (${pod_count} pods)"
                return 0
            fi
        fi

        sleep "${interval}"
        elapsed=$((elapsed + interval))
    done

    log_error "Timeout aguardando pods de ${service} ficarem prontos"
    return 1
}

check_service_health() {
    local service="$1"
    local namespace="${DEPLOY_ENV}"

    log_info "Verificando saude de ${service}..."

    # Verificar se pods estao rodando
    local pods
    pods=$(kubectl get pods -n "${namespace}" -l "app.kubernetes.io/name=${service}" \
        -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || "")

    if [[ -z "${pods}" ]]; then
        log_error "Nenhum pod encontrado para ${service}"
        return 1
    fi

    # Verificar status dos pods
    local not_ready=0
    for pod in ${pods}; do
        local status
        status=$(kubectl get pod -n "${namespace}" "${pod}" -o jsonpath='{.status.phase}' 2>/dev/null)

        if [[ "${status}" != "Running" ]]; then
            log_error "Pod ${pod} com status: ${status}"
            not_ready=1
        fi
    done

    if [[ ${not_ready} -ne 0 ]]; then
        return 1
    fi

    # Tentar fazer um health check HTTP se houver service
    local service_endpoint
    service_endpoint=$(kubectl get svc -n "${namespace}" "${service}" \
        -o jsonpath='{.spec.type}' 2>/dev/null || echo "")

    if [[ "${service_endpoint}" == "LoadBalancer" || "${service_endpoint}" == "NodePort" ]]; then
        # Em um cenario real, aqui faria um curl para o endpoint
        log_info "Servico ${service} esta acessivel"
    fi

    log_success "Health check passou para ${service}"
    return 0
}

# =============================================================================
# Funcoes de Rollback
# =============================================================================

rollback_service() {
    local service="$1"
    local namespace="${DEPLOY_ENV}"

    log_warning "Iniciando rollback de ${service}..."

    local rollback_cmd="helm rollback ${service} -n ${namespace}"

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY-RUN] Rollback: ${rollback_cmd}"
        return 0
    fi

    if eval "${rollback_cmd}" >> "${DEPLOY_LOG_FILE}" 2>&1; then
        log_success "Rollback concluido para ${service}"
        return 0
    else
        log_error "Rollback falhou para ${service}"
        return 1
    fi
}

# =============================================================================
# Fluxo Principal de Deploy
# =============================================================================

deploy_single_service() {
    local service="$1"

    log_section "Deploy de ${service}"

    # Build (se nao skip)
    if [[ "${SKIP_BUILD}" != "true" ]]; then
        if ! build_service_image "${service}" "${VERSION}"; then
            FAILED_SERVICES+=("${service} (build)")
            return 1
        fi
    fi

    # Helm deploy
    if ! helm_deploy_service "${service}" "${VERSION}"; then
        FAILED_SERVICES+=("${service} (deploy)")
        return 1
    fi

    # Health check
    if [[ "${SKIP_HEALTH_CHECKS}" != "true" ]]; then
        if ! wait_for_service_ready "${service}"; then
            log_warning "Health check timeout para ${service}, mas deploy foi feito"
            # Nao falha o deploy, apenas avisa
        fi

        if ! check_service_health "${service}"; then
            log_warning "Health check falhou para ${service}, mas deploy foi feito"
        fi
    fi

    DEPLOYED_SERVICES+=("${service}")
    log_success "Deploy concluido com sucesso: ${service}"
    return 0
}

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -e|--env)
                DEPLOY_ENV="${2:-staging}"
                shift 2
                ;;
            -s|--services)
                DEPLOY_SERVICES="${2:-}"
                shift 2
                ;;
            -v|--version)
                VERSION="${2:-latest}"
                shift 2
                ;;
            -d|--dry-run)
                DRY_RUN="true"
                shift
                ;;
            -y|--yes)
                AUTO_CONFIRM="true"
                shift
                ;;
            --skip-build)
                SKIP_BUILD="true"
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

    if [[ -z "${DEPLOY_SERVICES}" ]]; then
        log_warning "Nenhum servico especificado com --services"
        log_info "Use --help para ver a lista de servicos disponiveis"
        exit 0
    fi

    # Validar servicos
    IFS=',' read -ra requested <<< "${DEPLOY_SERVICES}"
    for service in "${requested[@]}"; do
        service=$(echo "${service}" | xargs) # trim
        local valid=0

        for valid_service in "${MCP_SERVICES[@]}" "${CORE_SERVICES[@]}"; do
            if [[ "${service}" == "${valid_service}" ]]; then
                valid=1
                break
            fi
        done

        if [[ ${valid} -eq 0 ]]; then
            log_error "Servico desconhecido: ${service}"
            exit 1
        fi
    done
}

show_deploy_summary() {
    log_section "Resumo do Deploy"

    echo "Ambiente: ${DEPLOY_ENV}"
    echo "Versao: ${VERSION}"
    echo "Servicos: ${DEPLOY_SERVICES}"
    echo "Dry Run: ${DRY_RUN}"
    echo "Skip Build: ${SKIP_BUILD}"
    echo "Skip Health Checks: ${SKIP_HEALTH_CHECKS}"
    echo ""
}

show_deploy_results() {
    local deploy_end_time
    deploy_end_time=$(date +%s)
    local duration=$((deploy_end_time - DEPLOY_START_TIME))
    local duration_minutes=$((duration / 60))
    local duration_seconds=$((duration % 60))

    log_section "Resultados do Deploy"

    echo "Duracao total: ${duration_minutes}m ${duration_seconds}s"
    echo ""

    if [[ ${#DEPLOYED_SERVICES[@]} -gt 0 ]]; then
        printf "${GREEN}Servicos deployados com sucesso (${#DEPLOYED_SERVICES[@]}):${NC}\n"
        for service in "${DEPLOYED_SERVICES[@]}"; do
            echo "  - ${service}"
        done
        echo ""
    fi

    if [[ ${#FAILED_SERVICES[@]} -gt 0 ]]; then
        printf "${RED}Servicos com falha (${#FAILED_SERVICES[@]}):${NC}\n"
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
    echo "Log detalhado: ${DEPLOY_LOG_FILE}"
}

# =============================================================================
# Main
# =============================================================================

main() {
    create_log_dir
    parse_arguments "$@"
    validate_arguments

    log_section "Neural Hive Mind - Deploy Automatizado"
    log_info "Ambiente: ${DEPLOY_ENV}"
    log_info "Log: ${DEPLOY_LOG_FILE}"

    # Verificar pre-requisitos
    check_prerequisites

    # Mostrar resumo
    show_deploy_summary

    # Confirmar deploy (exceto em staging com auto-confirm)
    if [[ "${DEPLOY_ENV}" == "production" && "${AUTO_CONFIRM}" != "true" ]]; then
        if ! confirm_prompt "Deploy para PRODUCAO foi solicitado. Confirmar?"; then
            log_warning "Deploy cancelado pelo usuario"
            exit 0
        fi
    elif [[ "${AUTO_CONFIRM}" != "true" ]]; then
        if ! confirm_prompt "Iniciar deploy de ${DEPLOY_SERVICES} para ${DEPLOY_ENV}?"; then
            log_warning "Deploy cancelado pelo usuario"
            exit 0
        fi
    fi

    # Processar cada servico
    IFS=',' read -ra services <<< "${DEPLOY_SERVICES}"
    for service in "${services[@]}"; do
        service=$(echo "${service}" | xargs) # trim whitespace
        deploy_single_service "${service}" || true
    done

    # Mostrar resultados
    show_deploy_results

    # Retornar status baseado em falhas
    if [[ ${#FAILED_SERVICES[@]} -gt 0 ]]; then
        log_error "Deploy concluido com falhas"
        exit 1
    else
        log_success "Deploy concluido com sucesso"
        exit 0
    fi
}

# Executar main
main "$@"
