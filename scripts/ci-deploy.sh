#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Neural Hive Mind - CI/CD Deploy Wrapper
# =============================================================================
#
# Script wrapper para CI/CD que executa o fluxo completo:
# 1. Build de imagens (opcional)
# 2. Push para registry (opcional)
# 3. Deploy via Helm
# 4. Validacao pos-deploy
# 5. Rollback automatico em caso de falha
#
# Uso:
#   ./scripts/ci-deploy.sh [opcoes]
#
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Cores
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

# Configuracoes
DEPLOY_ENV="${DEPLOY_ENV:-staging}"
SERVICES="${SERVICES:-}"
VERSION="${VERSION:-latest}"
SKIP_BUILD="${SKIP_BUILD:-false}"
SKIP_PUSH="${SKIP_PUSH:-false}"
SKIP_VALIDATION="${SKIP_VALIDATION:-false}"
AUTO_ROLLBACK="${AUTO_ROLLBACK:-true}"
DRY_RUN="${DRY_RUN:-false}"
CI_MODE="${CI_MODE:-false}"

# Registry de imagens
IMAGE_REGISTRY="${IMAGE_REGISTRY:-}"
IMAGE_TAG_PREFIX="${IMAGE_TAG_PREFIX:-}"

# Variaveis de tracking
DEPLOY_SUCCESSFUL=false
VALIDATION_SUCCESSFUL=false
ROLLBACK_EXECUTED=false

# =============================================================================
# Logging
# =============================================================================

log_info() {
    printf "%b[CI/CD] [INFO] %s%b\n" "${BLUE}" "$*" "${NC}" >&2
}

log_success() {
    printf "%b[CI/CD] \342\234\205 %s%b\n" "${GREEN}" "$*" "${NC}" >&2
}

log_error() {
    printf "%b[CI/CD] \342\235\214 %s%b\n" "${RED}" "$*" "${NC}" >&2
}

log_warning() {
    printf "%b[CI/CD] \342\234\205 %s%b\n" "${YELLOW}" "$*" "${NC}" >&2
}

log_section() {
    printf "\n%b========== %s ==========%b\n" "${CYAN}" "$*" "${NC}" >&2
}

# =============================================================================
# Funcoes de Build e Push
# =============================================================================

build_images() {
    local services="$1"

    log_section "Build de Imagens"

    if [[ "${SKIP_BUILD}" == "true" ]]; then
        log_info "Skip de build ativado"
        return 0
    fi

    log_info "Iniciando build de ${services}..."
    "${SCRIPT_DIR}/build.sh" --target "${services}" --push false || {
        log_error "Build de imagens falhou"
        return 1
    }

    log_success "Build de imagens concluido"
}

push_images() {
    local services="$1"

    log_section "Push para Registry"

    if [[ "${SKIP_PUSH}" == "true" ]]; then
        log_info "Skip de push ativado"
        return 0
    fi

    if [[ -z "${IMAGE_REGISTRY}" ]]; then
        log_warning "IMAGE_REGISTRY nao definido, pulando push"
        return 0
    fi

    log_info "Push de imagens para ${IMAGE_REGISTRY}..."
    "${SCRIPT_DIR}/build.sh" --target "${services}" --push true || {
        log_error "Push de imagens falhou"
        return 1
    }

    log_success "Push de imagens concluido"
}

# =============================================================================
# Funcoes de Deploy
# =============================================================================

deploy_services() {
    local services="$1"

    log_section "Deploy de Servicos"

    local deploy_args=(
        "--env" "${DEPLOY_ENV}"
        "--services" "${services}"
        "--version" "${VERSION}"
    )

    if [[ "${DRY_RUN}" == "true" ]]; then
        deploy_args+=("--dry-run")
    fi

    if [[ "${CI_MODE}" == "true" ]]; then
        deploy_args+=("--yes")
    fi

    log_info "Executando deploy com args: ${deploy_args[*]}"
    "${SCRIPT_DIR}/deploy-staging.sh" "${deploy_args[@]}" || {
        log_error "Deploy falhou"
        return 1
    }

    DEPLOY_SUCCESSFUL=true
    log_success "Deploy concluido com sucesso"
}

# =============================================================================
# Funcoes de Validacao
# =============================================================================

validate_deployment() {
    local services="$1"

    log_section "Validacao Pos-Deploy"

    if [[ "${SKIP_VALIDATION}" == "true" ]]; then
        log_info "Validacao desabilitada"
        VALIDATION_SUCCESSFUL=true
        return 0
    fi

    local validate_args=(
        "--env" "${DEPLOY_ENV}"
        "--services" "${services}"
        "--timeout" "300"
    )

    log_info "Executando validacao..."
    if "${SCRIPT_DIR}/validate-deployment.py" "${validate_args[@]}"; then
        VALIDATION_SUCCESSFUL=true
        log_success "Validacao passou"
        return 0
    else
        log_error "Validacao falhou"
        return 1
    fi
}

# =============================================================================
# Funcoes de Rollback
# =============================================================================

execute_rollback() {
    local services="$1"

    log_section "Rollback Automatico"

    if [[ "${AUTO_ROLLBACK}" != "true" ]]; then
        log_warning "Auto-rollback desabilitado"
        return 0
    fi

    if [[ "${DEPLOY_SUCCESSFUL}" != "true" ]]; then
        log_info "Deploy nao foi bem-sucedido, nao e necessario rollback"
        return 0
    fi

    log_warning "Iniciando rollback automatico devido a falha na validacao..."

    local rollback_args=(
        "--env" "${DEPLOY_ENV}"
        "--services" "${services}"
        "--yes"
        "--skip-health-checks"
    )

    if "${SCRIPT_DIR}/rollback-staging.sh" "${rollback_args[@]}"; then
        ROLLBACK_EXECUTED=true
        log_success "Rollback executado com sucesso"
        return 0
    else
        log_error "Rollback falhou!"
        return 1
    fi
}

# =============================================================================
# Funcoes de Relatorio
# =============================================================================

show_final_report() {
    log_section "Relatorio Final CI/CD"

    echo "Deploy: $([ "${DEPLOY_SUCCESSFUL}" = true ] && echo "${GREEN}SUCESSO${NC}" || echo "${RED}FALHOU${NC}")"
    echo "Validacao: $([ "${VALIDATION_SUCCESSFUL}" = true ] && echo "${GREEN}SUCESSO${NC}" || echo "${RED}FALHOU${NC}")"
    echo "Rollback: $([ "${ROLLBACK_EXECUTED}" = true ] && echo "${YELLOW}EXECUTADO${NC}" || echo "NAO NECESSARIO")"

    if [[ "${DEPLOY_SUCCESSFUL}" = true && "${VALIDATION_SUCCESSFUL}" = true ]]; then
        log_success "CI/CD pipeline completado com sucesso"
        return 0
    else
        log_error "CI/CD pipeline falhou"
        return 1
    fi
}

# =============================================================================
# Parse de Argumentos
# =============================================================================

show_help() {
    cat << EOF
${CYAN}Neural Hive Mind - CI/CD Deploy Wrapper${NC}

${YELLOW}Uso:${NC}
  $0 [opcoes]

${YELLOW}Opcoes:${NC}
  -e, --env ENV           Ambiente (staging|production, padrao: staging)
  -s, --services LIST     Lista de servicos separados por virgula
  -v, --version VERSION   Versao das imagens (padrao: latest)
  --skip-build            Pular build de imagens
  --skip-push             Pular push para registry
  --skip-validation       Pular validacao pos-deploy
  --no-auto-rollback      Desabilitar rollback automatico
  -d, --dry-run           Simular deploy sem modificar ambiente
  --ci                    Modo CI (auto-confirma)
  -h, --help              Mostrar esta ajuda

${YELLOW}Variaveis de Ambiente:${NC}
  IMAGE_REGISTRY          Registry para push de imagens
  IMAGE_TAG_PREFIX        Prefixo para tags de imagem
  DEPLOY_ENV              Ambiente (staging|production)
  SERVICES                Lista de servicos
  VERSION                 Versao para deploy

${YELLOW}Exemplos:${NC}
  # Deploy completo para staging
  $0 --env staging --services queen-mcp-server --ci

  # Deploy sem build (imagens ja existem)
  $0 --services queen-mcp-server --skip-build --skip-push

  # Deploy para producao com validacao
  $0 --env production --services queen-mcp-server --version v1.2.3

EOF
}

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -e|--env)
                DEPLOY_ENV="${2:-staging}"
                shift 2
                ;;
            -s|--services)
                SERVICES="${2:-}"
                shift 2
                ;;
            -v|--version)
                VERSION="${2:-latest}"
                shift 2
                ;;
            --skip-build)
                SKIP_BUILD="true"
                shift
                ;;
            --skip-push)
                SKIP_PUSH="true"
                shift
                ;;
            --skip-validation)
                SKIP_VALIDATION="true"
                shift
                ;;
            --no-auto-rollback)
                AUTO_ROLLBACK="false"
                shift
                ;;
            -d|--dry-run)
                DRY_RUN="true"
                shift
                ;;
            --ci)
                CI_MODE="true"
                shift
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

    # Validar argumentos obrigatorios
    if [[ -z "${SERVICES}" ]]; then
        log_error "--services e obrigatorio"
        show_help
        exit 1
    fi

    if [[ "${DEPLOY_ENV}" != "staging" && "${DEPLOY_ENV}" != "production" ]]; then
        log_error "Ambiente invalido: ${DEPLOY_ENV}"
        exit 1
    fi
}

# =============================================================================
# Main
# =============================================================================

main() {
    log_section "Neural Hive Mind - CI/CD Pipeline"
    log_info "Ambiente: ${DEPLOY_ENV}"
    log_info "Servicos: ${SERVICES}"
    log_info "Versao: ${VERSION}"
    log_info "Auto-rollback: ${AUTO_ROLLBACK}"

    # Parse argumentos
    parse_arguments "$@"

    # 1. Build de imagens
    if ! build_images "${SERVICES}"; then
        log_error "Pipeline falhou na etapa de build"
        exit 1
    fi

    # 2. Push para registry
    if ! push_images "${SERVICES}"; then
        log_error "Pipeline falhou na etapa de push"
        exit 1
    fi

    # 3. Deploy
    if ! deploy_services "${SERVICES}"; then
        log_error "Pipeline falhou na etapa de deploy"
        show_final_report
        exit 1
    fi

    # 4. Validacao
    if ! validate_deployment "${SERVICES}"; then
        log_error "Pipeline falhou na etapa de validacao"

        # Rollback automatico se configurado
        execute_rollback "${SERVICES}"

        show_final_report
        exit 1
    fi

    # 5. Relatorio final
    show_final_report
    exit 0
}

# Executar main
main "$@"
