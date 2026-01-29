#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
source "${SCRIPT_DIR}/lib/docker.sh"
source "${SCRIPT_DIR}/lib/k8s.sh"
source "${SCRIPT_DIR}/lib/aws.sh"

PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MODULES_DIR="${SCRIPT_DIR}/deploy/modules"

DEPLOY_ENV="${DEPLOY_ENV:-local}"
DEPLOY_PHASE="${DEPLOY_PHASE:-1}"
DEPLOY_SERVICES="${DEPLOY_SERVICES:-}"
DRY_RUN="${DRY_RUN:-false}"
SKIP_VALIDATION="${SKIP_VALIDATION:-false}"
VERSION="${VERSION:-latest}"

VALID_SERVICES=(
    foundation
    infrastructure
    security
    observability
    gateway
    ste
    specialists
    consensus
    memory
    orchestrator
    workers
    code-forge
    queen-agent
    scout-agents
    guard-agents
)

declare -A COMPONENT_DEPENDENCIES=(
    ["gateway"]="kafka redis"
    ["specialists"]="mongodb mlflow kafka"
    ["consensus"]="gateway specialists redis"
    ["memory"]="mongodb neo4j redis"
    ["orchestrator"]="temporal kafka mongodb"
    ["workers"]="orchestrator kafka"
)

declare -a DEPLOYED_COMPONENTS=()
declare -a FAILED_COMPONENTS=()
DEPLOY_DURATION=0
DEPLOY_START_TIME=$(date +%s)

trim() {
    local var="$*"
    var="${var#"${var%%[![:space:]]*}"}"
    var="${var%"${var##*[![:space:]]}"}"
    echo "${var}"
}

execute_deploy_command() {
    local command="$1"
    local dry_run="${2:-${DRY_RUN}}"

    if [[ "${dry_run}" == "true" ]]; then
        log_info "[DRY-RUN] ${command}"
        return 0
    fi

    log_debug "Executando comando: ${command}"
    eval "${command}"
}

run_deploy_module() {
    local component="$1"
    local func="$2"
    local env="$3"
    local dry_run="${4:-${DRY_RUN}}"

    if [[ "${SKIP_VALIDATION}" != "true" ]]; then
        if ! validate_dependencies "${component}" "${env}"; then
            FAILED_COMPONENTS+=("${component}")
            return 1
        fi
    else
        log_debug "Validação de dependências desabilitada para ${component}"
    fi

    log_info "Deploying component: ${component}"
    if "${func}" "${env}" "${dry_run}"; then
        DEPLOYED_COMPONENTS+=("${component}")
        return 0
    fi

    FAILED_COMPONENTS+=("${component}")
    return 1
}

deploy_service() {
    local service="$1"
    local env="$2"
    local dry_run="${3:-${DRY_RUN}}"
    local module_path

    log_info "Preparando deploy de ${service} (versão ${VERSION}) para ${env}"
    case "${service}" in
        foundation)
            module_path="${MODULES_DIR}/foundation.sh"
            ;;
        infrastructure)
            module_path="${MODULES_DIR}/infrastructure.sh"
            ;;
        security)
            module_path="${MODULES_DIR}/security.sh"
            ;;
        observability)
            module_path="${MODULES_DIR}/observability.sh"
            ;;
        gateway)
            module_path="${MODULES_DIR}/phase1/gateway.sh"
            ;;
        ste)
            module_path="${MODULES_DIR}/phase1/ste.sh"
            ;;
        specialists)
            module_path="${MODULES_DIR}/phase1/specialists.sh"
            ;;
        consensus)
            module_path="${MODULES_DIR}/phase1/consensus.sh"
            ;;
        memory)
            module_path="${MODULES_DIR}/phase1/memory.sh"
            ;;
        orchestrator)
            module_path="${MODULES_DIR}/phase2/orchestrator.sh"
            ;;
        workers)
            module_path="${MODULES_DIR}/phase2/workers.sh"
            ;;
        code-forge)
            module_path="${MODULES_DIR}/phase2/code-forge.sh"
            ;;
        queen-agent)
            module_path="${MODULES_DIR}/phase2/queen-agent.sh"
            ;;
        scout-agents)
            module_path="${MODULES_DIR}/phase2/scout-agents.sh"
            ;;
        guard-agents)
            module_path="${MODULES_DIR}/phase2/guard-agents.sh"
            ;;
        *)
            log_error "Serviço desconhecido para deploy: ${service}"
            return 1
            ;;
    esac

    if [[ ! -f "${module_path}" ]]; then
        log_error "Módulo não encontrado: ${module_path}"
        return 1
    fi

    source "${module_path}"
    run_deploy_module "${service}" "deploy_${service//-/_}" "${env}" "${dry_run}"
}

deploy_service_list() {
    local env="$1"
    local dry_run="${2:-${DRY_RUN}}"

    [[ -z "${DEPLOY_SERVICES}" ]] && return 0

    IFS=',' read -ra requested <<< "${DEPLOY_SERVICES}"
    for raw_service in "${requested[@]}"; do
        local normalized
        normalized="$(trim "${raw_service}")"
        normalized="${normalized,,}"
        normalized="${normalized// /}"
        if [[ -z "${normalized}" ]]; then
            continue
        fi

        deploy_service "${normalized}" "${env}" "${dry_run}"
    done
}

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -e|--env)
                DEPLOY_ENV="${2:-}"
                shift 2
                ;;
            -p|--phase)
                DEPLOY_PHASE="${2:-}"
                shift 2
                ;;
            -s|--services)
                DEPLOY_SERVICES="${2:-}"
                DEPLOY_SERVICES="${DEPLOY_SERVICES,,}"
                DEPLOY_SERVICES="${DEPLOY_SERVICES// /}"
                shift 2
                ;;
            -v|--version)
                VERSION="${2:-}"
                shift 2
                ;;
            -d|--dry-run)
                DRY_RUN="true"
                shift
                ;;
            --skip-validation)
                SKIP_VALIDATION="true"
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "Opção desconhecida: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

validate_environment() {
    local valid_envs=("local" "eks" "minikube")
    local valid_phases=("foundation" "1" "2" "all")

    if [[ ! " ${valid_envs[*]} " =~ " ${DEPLOY_ENV} " ]]; then
        log_error "Ambiente inválido: ${DEPLOY_ENV}"
        return 1
    fi

    if [[ ! " ${valid_phases[*]} " =~ " ${DEPLOY_PHASE} " ]]; then
        log_error "Fase inválida: ${DEPLOY_PHASE}"
        return 1
    fi

    if [[ -n "${DEPLOY_SERVICES}" ]]; then
        IFS=',' read -ra requested <<< "${DEPLOY_SERVICES}"
        for service in "${requested[@]}"; do
            service="${service,,}"
            service="${service// /}"
            if [[ -z "${service}" ]]; then
                continue
            fi
            if [[ ! " ${VALID_SERVICES[*]} " =~ " ${service} " ]]; then
                log_error "Serviço inválido: ${service}"
                return 1
            fi
        done
    fi

    log_success "Ambiente validado (env=${DEPLOY_ENV}, phase=${DEPLOY_PHASE})"
}

validate_dependencies() {
    local component="$1"
    local env="$2"

    if [[ -z "${COMPONENT_DEPENDENCIES[${component}]:-}" ]]; then
        log_debug "Nenhuma dependência configurada para ${component}"
        return 0
    fi

    log_info "Validando dependências para ${component}..."
    local deps="${COMPONENT_DEPENDENCIES[${component}]}"

    for dep in ${deps}; do
        if ! check_component_deployed "${dep}" "${env}"; then
            log_error "Dependência não satisfeita: ${dep}"
            log_info "Execute: ${SCRIPT_DIR}/deploy.sh --env ${env} --services ${dep}"
            return 1
        fi
        log_success "Dependência confirmada: ${dep}"
    done

    return 0
}

check_component_deployed() {
    local component="$1"
    local env="$2"

    case "${component}" in
        kafka)
            k8s_resource_exists statefulset neural-hive-kafka || return 1
            ;;
        redis)
            k8s_resource_exists statefulset redis || return 1
            ;;
        mongodb)
            k8s_resource_exists statefulset mongodb || return 1
            ;;
        neo4j)
            k8s_resource_exists statefulset neo4j || return 1
            ;;
        mlflow)
            k8s_resource_exists deployment mlflow || return 1
            ;;
        temporal)
            k8s_resource_exists statefulset temporal || return 1
            ;;
        gateway|specialists|memory|consensus|workers|orchestrator|code-forge)
            k8s_test_service_connectivity default "${component}" >/dev/null 2>&1 || return 1
            ;;
        *)
            log_debug "Não há verificações automáticas para ${component}"
            return 0
            ;;
    esac

    return 0
}

deploy_phase1_common() {
    local env="$1"
    local dry_run="${2:-${DRY_RUN}}"
    local services=(gateway ste specialists consensus memory)

    for service in "${services[@]}"; do
        deploy_service "${service}" "${env}" "${dry_run}"
    done
}

deploy_phase2_common() {
    local env="$1"
    local dry_run="${2:-${DRY_RUN}}"
    local services=(orchestrator workers code-forge queen-agent scout-agents guard-agents)

    for service in "${services[@]}"; do
        deploy_service "${service}" "${env}" "${dry_run}"
    done
}

deploy_phase1_local() {
    log_section "Phase 1 - Local"
    deploy_service "infrastructure" "local"

    if [[ -n "${DEPLOY_SERVICES}" ]]; then
        deploy_service_list "local"
    else
        deploy_phase1_common "local" "${DRY_RUN}"
    fi
}

deploy_phase2_local() {
    log_section "Phase 2 - Local"

    if [[ -n "${DEPLOY_SERVICES}" ]]; then
        deploy_service_list "local"
    else
        deploy_phase2_common "local" "${DRY_RUN}"
    fi
}

deploy_phase1_eks() {
    log_section "Phase 1 - EKS"
    deploy_service "infrastructure" "eks"

    if [[ -n "${DEPLOY_SERVICES}" ]]; then
        deploy_service_list "eks"
    else
        deploy_phase1_common "eks" "${DRY_RUN}"
    fi
}

deploy_phase2_eks() {
    log_section "Phase 2 - EKS"

    if [[ -n "${DEPLOY_SERVICES}" ]]; then
        deploy_service_list "eks"
    else
        deploy_phase2_common "eks" "${DRY_RUN}"
    fi
}

deploy_foundation_eks() {
    log_section "Foundation - EKS"
    deploy_service "foundation" "eks"
    deploy_service "security" "eks"
    deploy_service "observability" "eks"
}

deploy_local() {
    log_phase "Deploy Local (Minikube)"

    check_command_exists minikube || {
        log_error "Minikube não encontrado"
        exit 1
    }

    if ! minikube status >/dev/null 2>&1; then
        log_error "Minikube não está rodando"
        exit 1
    fi

    case "${DEPLOY_PHASE}" in
        foundation)
            deploy_service "infrastructure" "local"
            deploy_service "security" "local"
            deploy_service "observability" "local"
            ;;
        1)
            deploy_phase1_local
            ;;
        2)
            deploy_phase2_local
            ;;
        all)
            deploy_phase1_local
            deploy_phase2_local
            ;;
        *)
            log_warning "Fase ${DEPLOY_PHASE} não mapeada para local"
            ;;
    esac
}

deploy_minikube() {
    deploy_local
}

deploy_eks() {
    log_phase "Deploy EKS"

    aws_check_credentials || {
        log_error "Credenciais AWS inválidas"
        exit 1
    }

    local cluster_name="${CLUSTER_NAME:-neural-hive-${DEPLOY_ENV}}"

    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_error "Não conectado a nenhum cluster EKS"
        log_info "Execute: aws eks update-kubeconfig --name ${cluster_name} --region ${AWS_REGION:-us-east-1}"
        exit 1
    fi

    case "${DEPLOY_PHASE}" in
        foundation)
            deploy_foundation_eks
            ;;
        1)
            deploy_phase1_eks
            ;;
        2)
            deploy_phase2_eks
            ;;
        all)
            deploy_foundation_eks
            deploy_phase1_eks
            deploy_phase2_eks
            ;;
        *)
            log_warning "Fase ${DEPLOY_PHASE} não reconhecida em EKS"
            ;;
    esac
}

show_help() {
    cat <<EOF
Neural Hive-Mind - Deploy CLI Unificado

USAGE:
    ./scripts/deploy.sh [OPTIONS]

OPTIONS:
    -e, --env ENV           Ambiente: local, eks, minikube (default: local)
    -p, --phase PHASE       Fase: foundation, 1, 2, all (default: 1)
    -s, --services LIST     Serviços específicos (comma-separated)
    -v, --version VERSION   Versão das imagens (default: latest)
    -d, --dry-run           Executar em modo dry-run
    --skip-validation       Pular validação de dependências
    -h, --help              Mostrar esta ajuda

ENVIRONMENTS:
    local       Deploy em Minikube local
    eks         Deploy em Amazon EKS
    minikube    Alias para local

PHASES:
    foundation  Terraform + Security + Observability (apenas EKS)
    1           Phase 1: Gateway, STE, Specialists, Consensus, Memory
    2           Phase 2: Orchestrator, Workers, Code Forge, Agents
    all         Todas as fases

EXAMPLES:
    ./scripts/deploy.sh --env local --phase 1
    ./scripts/deploy.sh --env eks --services gateway
    ./scripts/deploy.sh --env eks --phase 2 --version 1.0.8
    ./scripts/deploy.sh --env eks --phase all --dry-run
    ./scripts/deploy.sh --env local --services gateway,specialists,consensus

DEPENDENCIES:
    O CLI valida automaticamente dependências entre componentes.
    Use --skip-validation para pular esta verificação.

MIGRATION:
    Scripts antigos foram deprecados, use o novo CLI:
        deploy-gateway.sh        → deploy.sh --services gateway
        deploy-specialists.sh    → deploy.sh --services specialists
        deploy-eks-complete.sh   → deploy.sh --env eks --phase all
        deploy-infrastructure-local.sh → deploy.sh --env local --phase foundation

EOF
}

generate_deploy_report() {
    mkdir -p "${PROJECT_ROOT}/logs"
    local report_file="${PROJECT_ROOT}/logs/deploy-report-${DEPLOY_ENV}-${DEPLOY_PHASE}-$(date +%Y%m%d-%H%M%S).json"
    local deployed_json="[]"
    local failed_json="[]"

    if [[ ${#DEPLOYED_COMPONENTS[@]} -gt 0 ]]; then
        deployed_json=$(printf '%s\n' "${DEPLOYED_COMPONENTS[@]}" | jq -R . | jq -s .)
    fi

    if [[ ${#FAILED_COMPONENTS[@]} -gt 0 ]]; then
        failed_json=$(printf '%s\n' "${FAILED_COMPONENTS[@]}" | jq -R . | jq -s .)
    fi

    cat > "${report_file}" <<EOF
{
  "deploy_metadata": {
    "timestamp": "$(date -Iseconds)",
    "environment": "${DEPLOY_ENV}",
    "phase": "${DEPLOY_PHASE}",
    "services": "${DEPLOY_SERVICES}",
    "version": "${VERSION}",
    "dry_run": ${DRY_RUN}
  },
  "components_deployed": ${deployed_json},
  "failed_components": ${failed_json},
  "duration_seconds": ${DEPLOY_DURATION}
}
EOF

    log_success "Relatório salvo em: ${report_file}"
}

cleanup() {
    local exit_code=$?
    DEPLOY_DURATION=$(( $(date +%s) - DEPLOY_START_TIME ))
    generate_deploy_report || true

    if [[ "${exit_code}" -eq 0 ]]; then
        log_success "Deploy concluído (${DEPLOY_DURATION}s)"
    else
        log_error "Deploy interrompido (${DEPLOY_DURATION}s) com código ${exit_code}"
    fi
}
trap cleanup EXIT

main() {
    parse_arguments "$@"
    validate_environment || exit 1
    check_prerequisites || log_warning "Pré-requisitos básicos podem estar faltando"

    case "${DEPLOY_ENV}" in
        local)
            deploy_local
            ;;
        minikube)
            deploy_minikube
            ;;
        eks)
            deploy_eks
            ;;
        *)
            log_error "Ambiente inválido: ${DEPLOY_ENV}"
            return 1
            ;;
    esac
}

main "$@"
