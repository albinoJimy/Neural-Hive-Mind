#!/bin/bash
set -euo pipefail

# ==============================================================================
# Push de Imagens Docker para ECR com Paralelização e Retry Logic
# ==============================================================================
# Script para fazer push paralelo de imagens Docker locais para ECR
# Baseado no padrão estabelecido por build-local-parallel.sh
#
# Uso:
#   ./scripts/push-to-ecr.sh [--version <ver>] [--parallel <n>] [--services <list>]
#
# Exemplos:
#   ./scripts/push-to-ecr.sh
#   ./scripts/push-to-ecr.sh --version 1.0.8 --parallel 8
#   ./scripts/push-to-ecr.sh --services "gateway-intencoes,consensus-engine"
# ==============================================================================

# Cores para logging
readonly GREEN='\033[0;32m'
readonly BLUE='\033[0;34m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly NC='\033[0m' # No Color

# Configuração
VERSION="${VERSION:-1.0.7}"
MAX_PARALLEL_JOBS="${MAX_PARALLEL_JOBS:-4}"
MAX_RETRIES=3
RETRY_DELAY_BASE=2
LOCAL_IMAGE_PREFIX="neural-hive-mind"

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Diretório de semáforo único por execução
SEMAPHORE_DIR="/tmp/push-semaphore-$$"

# Lista de serviços Phase 1
SERVICES=(
    "gateway-intencoes"
    "semantic-translation-engine"
    "specialist-business"
    "specialist-technical"
    "specialist-architecture"
    "specialist-behavior"
    "specialist-evolution"
    "consensus-engine"
    "memory-layer-api"
)

# Arrays de tracking
declare -a PUSH_PIDS=()
declare -a FAILED_SERVICES=()
declare -a SUCCESS_SERVICES=()

# Contadores
total=0
completed=0
failed=0
success=0

# ==============================================================================
# Funções de Logging
# ==============================================================================

log_info() {
    echo -e "${BLUE}[INFO]$(date +'%H:%M:%S')${NC} $*"
}

log_success() {
    echo -e "${GREEN}✅ $*${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $*${NC}"
}

log_error() {
    echo -e "${RED}❌ $*${NC}"
}

log_progress() {
    echo -e "${BLUE}[$1/$2]${NC} $3"
}

# ==============================================================================
# Função de Pré-requisitos
# ==============================================================================

check_prerequisites() {
    log_info "Verificando pré-requisitos..."

    # Verificar Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker não encontrado. Instale o Docker primeiro."
        exit 1
    fi

    if ! docker info &> /dev/null; then
        log_error "Docker daemon não está rodando."
        exit 1
    fi
    log_success "Docker instalado e rodando"

    # Verificar AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI não encontrado. Instale o AWS CLI primeiro."
        exit 1
    fi
    log_success "AWS CLI instalado"

    # Verificar credenciais AWS
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "Credenciais AWS inválidas. Execute 'aws configure'."
        exit 1
    fi
    log_success "Credenciais AWS válidas"

    # Carregar variáveis de ambiente
    if [[ -f "${HOME}/.neural-hive-env" ]]; then
        log_info "Carregando variáveis de ${HOME}/.neural-hive-env"
        # shellcheck disable=SC1090
        source "${HOME}/.neural-hive-env"
    fi

    # Validar variáveis obrigatórias
    ENV="${ENV:-dev}"
    AWS_REGION="${AWS_REGION:-us-east-1}"

    # Derivar AWS_ACCOUNT_ID
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    if [[ -z "${AWS_ACCOUNT_ID}" ]]; then
        log_error "Não foi possível obter AWS Account ID"
        exit 1
    fi

    # Derivar ECR_REGISTRY
    ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

    # Exibir configuração
    echo ""
    log_info "=== Configuração ==="
    echo "  Ambiente:    ${ENV}"
    echo "  Região:      ${AWS_REGION}"
    echo "  Account ID:  ${AWS_ACCOUNT_ID}"
    echo "  ECR Registry: ${ECR_REGISTRY}"
    echo "  Versão:      ${VERSION}"
    echo ""
}

# ==============================================================================
# Função de Login ECR
# ==============================================================================

ecr_login() {
    log_info "Fazendo login no ECR..."

    local attempt=1
    while [[ ${attempt} -le ${MAX_RETRIES} ]]; do
        log_info "Tentativa ${attempt}/${MAX_RETRIES} de login no ECR"

        set +e
        if aws ecr get-login-password --region "${AWS_REGION}" | \
           docker login --username AWS --password-stdin "${ECR_REGISTRY}" &> /dev/null; then
            set -e
            log_success "Login no ECR bem-sucedido"
            return 0
        fi
        set -e

        if [[ ${attempt} -lt ${MAX_RETRIES} ]]; then
            local delay=$((RETRY_DELAY_BASE ** attempt))
            log_warning "Login falhou. Tentando novamente em ${delay}s..."
            sleep "${delay}"
        fi

        ((attempt++))
    done

    log_error "Login no ECR falhou após ${MAX_RETRIES} tentativas"
    return 1
}

# ==============================================================================
# Função de Criação de Repositório ECR
# ==============================================================================

create_ecr_repository() {
    local repo_name="$1"

    # Verificar se repositório existe
    set +e
    aws ecr describe-repositories \
        --repository-names "${repo_name}" \
        --region "${AWS_REGION}" &> /dev/null
    local exists=$?
    set -e

    if [[ ${exists} -eq 0 ]]; then
        return 0
    fi

    # Criar repositório com retry
    log_info "Criando repositório ECR: ${repo_name}"

    local attempt=1
    while [[ ${attempt} -le ${MAX_RETRIES} ]]; do
        set +e
        if aws ecr create-repository \
            --repository-name "${repo_name}" \
            --region "${AWS_REGION}" \
            --image-scanning-configuration scanOnPush=true \
            --encryption-configuration encryptionType=AES256 &> /dev/null; then
            set -e
            log_success "Repositório ${repo_name} criado"
            return 0
        fi
        set -e

        if [[ ${attempt} -lt ${MAX_RETRIES} ]]; then
            local delay=$((RETRY_DELAY_BASE ** attempt))
            log_warning "Criação falhou. Tentando novamente em ${delay}s..."
            sleep "${delay}"
        fi

        ((attempt++))
    done

    log_error "Criação do repositório ${repo_name} falhou após ${MAX_RETRIES} tentativas"
    return 1
}

# ==============================================================================
# Função de Validação de Imagem Local
# ==============================================================================

validate_local_image() {
    local service="$1"

    if ! docker image inspect "${LOCAL_IMAGE_PREFIX}/${service}:latest" &> /dev/null; then
        log_error "Imagem local não encontrada: ${LOCAL_IMAGE_PREFIX}/${service}:latest"
        return 1
    fi

    if ! docker image inspect "${LOCAL_IMAGE_PREFIX}/${service}:${VERSION}" &> /dev/null; then
        log_error "Imagem local não encontrada: ${LOCAL_IMAGE_PREFIX}/${service}:${VERSION}"
        return 1
    fi

    return 0
}

# ==============================================================================
# Função de Push com Retry
# ==============================================================================

push_service_with_retry() {
    local target_image="$1"

    local attempt=1
    while [[ ${attempt} -le ${MAX_RETRIES} ]]; do
        echo "Tentativa ${attempt}/${MAX_RETRIES} de push: ${target_image}"

        set +e
        if docker push "${target_image}"; then
            set -e
            echo "Push bem-sucedido: ${target_image}"
            return 0
        fi
        set -e

        if [[ ${attempt} -lt ${MAX_RETRIES} ]]; then
            local delay=$((RETRY_DELAY_BASE ** attempt))
            echo "Push falhou. Tentando novamente em ${delay}s..."
            sleep "${delay}"
        fi

        ((attempt++))
    done

    echo "ERRO: Push falhou após ${MAX_RETRIES} tentativas: ${target_image}"
    return 1
}

# ==============================================================================
# Função de Push de Serviço
# ==============================================================================

push_service() {
    local service="$1"
    local local_image_latest="${LOCAL_IMAGE_PREFIX}/${service}:latest"
    local local_image_version="${LOCAL_IMAGE_PREFIX}/${service}:${VERSION}"
    local ecr_repo="neural-hive-${ENV}/${service}"
    local ecr_image_latest="${ECR_REGISTRY}/${ecr_repo}:latest"
    local ecr_image_version="${ECR_REGISTRY}/${ecr_repo}:${VERSION}"
    local log_file="${PROJECT_ROOT}/logs/push-${service}.log"

    # Redirecionar output para log
    exec > "${log_file}" 2>&1

    # Validar imagem local
    if ! validate_local_image "${service}"; then
        return 1
    fi

    # Criar repositório ECR
    if ! create_ecr_repository "${ecr_repo}"; then
        return 1
    fi

    # Re-tag imagens locais para ECR
    if ! docker tag "${local_image_latest}" "${ecr_image_latest}"; then
        echo "Falha ao criar tag ${ecr_image_latest}"
        return 1
    fi

    if ! docker tag "${local_image_version}" "${ecr_image_version}"; then
        echo "Falha ao criar tag ${ecr_image_version}"
        return 1
    fi

    # Push tag latest
    echo "Fazendo push de ${ecr_image_latest}..."
    if ! push_service_with_retry "${ecr_image_latest}"; then
        echo "Falha ao fazer push de ${ecr_image_latest}"
        return 1
    fi

    # Push tag version
    echo "Fazendo push de ${ecr_image_version}..."
    if ! push_service_with_retry "${ecr_image_version}"; then
        echo "Falha ao fazer push de ${ecr_image_version}"
        return 1
    fi

    echo "Push concluído com sucesso para ${service}"
    return 0
}

# ==============================================================================
# Função de Controle de Concorrência
# ==============================================================================

acquire_slot() {
    while [[ $(jobs -r | wc -l) -ge ${MAX_PARALLEL_JOBS} ]]; do
        sleep 0.5
    done
}

# ==============================================================================
# Função de Progresso
# ==============================================================================

show_progress() {
    local current=$1
    local total=$2
    local percent=$((current * 100 / total))
    local filled=$((percent / 5))
    local empty=$((20 - filled))

    printf "\r${BLUE}Progresso: [${NC}"
    printf "%${filled}s" | tr ' ' '='
    printf ">"
    printf "%${empty}s" | tr ' ' ' '
    printf "${BLUE}] %d%% (%d/%d)${NC}" "${percent}" "${current}" "${total}"
}

# ==============================================================================
# Função de Cleanup
# ==============================================================================

cleanup() {
    log_info "Limpando recursos..."

    # Matar jobs em background
    local pids
    pids=$(jobs -p)
    if [[ -n "${pids}" ]]; then
        # shellcheck disable=SC2086
        kill ${pids} 2>/dev/null || true
    fi

    # Remover diretório temporário específico desta execução
    rm -rf "${SEMAPHORE_DIR}"
}

trap cleanup EXIT INT TERM

# ==============================================================================
# Função de Ajuda
# ==============================================================================

print_help() {
    cat << EOF
Uso: $0 [opções]

Script para fazer push paralelo de imagens Docker locais para ECR.

Opções:
  --version <ver>       Versão das imagens (padrão: ${VERSION})
  --parallel <n>        Número de pushes paralelos (padrão: ${MAX_PARALLEL_JOBS})
  --services <list>     Lista de serviços separados por vírgula
  --env <env>           Ambiente (dev, staging, prod) (padrão: ${ENV:-dev})
  --region <region>     Região AWS (padrão: ${AWS_REGION:-us-east-1})
  --help                Exibir esta ajuda

Exemplos:
  $0
  $0 --version 1.0.8 --parallel 8
  $0 --services "gateway-intencoes,consensus-engine"
  $0 --env staging --region us-west-2

Pré-requisitos:
  - AWS CLI configurado (aws configure)
  - Credenciais AWS válidas
  - Docker instalado e rodando
  - Imagens buildadas localmente (executar build-local-parallel.sh primeiro)

EOF
    exit 0
}

# ==============================================================================
# Parsing de Argumentos CLI
# ==============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --parallel)
            MAX_PARALLEL_JOBS="$2"
            shift 2
            ;;
        --services)
            IFS=',' read -ra SERVICES <<< "$2"
            shift 2
            ;;
        --env)
            ENV="$2"
            shift 2
            ;;
        --region)
            AWS_REGION="$2"
            shift 2
            ;;
        --help)
            print_help
            ;;
        *)
            log_error "Opção desconhecida: $1"
            print_help
            ;;
    esac
done

# ==============================================================================
# Função Principal
# ==============================================================================

main() {
    cd "${PROJECT_ROOT}"

    # Banner
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║        Push de Imagens Docker para ECR (Paralelo)             ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "  Versão:          ${VERSION}"
    echo "  Jobs Paralelos:  ${MAX_PARALLEL_JOBS}"
    echo "  Total Serviços:  ${#SERVICES[@]}"
    echo ""

    # Verificar pré-requisitos
    check_prerequisites

    # Criar diretório de logs
    mkdir -p logs

    # Login ECR
    if ! ecr_login; then
        log_error "Não foi possível fazer login no ECR. Abortando."
        exit 1
    fi

    # Criar diretório temporário único para semáforo
    rm -rf "${SEMAPHORE_DIR}"
    mkdir -p "${SEMAPHORE_DIR}"

    # Registrar tempo de início
    local start_time
    start_time=$(date +%s)

    total=${#SERVICES[@]}

    log_info "Iniciando push de ${total} serviços..."
    echo ""

    # Loop pelos serviços
    local index=1
    for service in "${SERVICES[@]}"; do
        acquire_slot

        log_progress "${index}" "${total}" "Iniciando push: ${service}"

        # Iniciar push em background
        (
            if push_service "${service}"; then
                echo "SUCCESS:${service}" > "${SEMAPHORE_DIR}/${service}.status"
            else
                echo "FAILED:${service}" > "${SEMAPHORE_DIR}/${service}.status"
            fi
        ) &

        PUSH_PIDS+=($!)
        ((index++))
    done

    # Aguardar conclusão de todos os jobs
    echo ""
    log_info "Aguardando conclusão dos pushes..."

    for pid in "${PUSH_PIDS[@]}"; do
        wait "${pid}" || true
        ((completed++))
        show_progress "${completed}" "${total}"
    done

    echo ""
    echo ""

    # Coletar resultados
    for service in "${SERVICES[@]}"; do
        local status_file="${SEMAPHORE_DIR}/${service}.status"
        if [[ -f "${status_file}" ]]; then
            local status
            status=$(cat "${status_file}")
            if [[ "${status}" == SUCCESS:* ]]; then
                SUCCESS_SERVICES+=("${service}")
                ((success++))
            else
                FAILED_SERVICES+=("${service}")
                ((failed++))
            fi
        else
            FAILED_SERVICES+=("${service}")
            ((failed++))
        fi
    done

    # Calcular duração
    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local minutes=$((duration / 60))
    local seconds=$((duration % 60))

    # Exibir resumo
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                      Resumo do Push                            ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    if [[ ${failed} -eq 0 ]]; then
        log_success "Todos os pushes foram concluídos com sucesso! (${success}/${total})"
    else
        log_warning "Pushes concluídos: ${success}/${total}"
        log_error "Pushes falhados: ${failed}/${total}"
    fi

    echo ""
    echo "  Tempo total:      ${minutes}m ${seconds}s"

    if [[ ${minutes} -gt 0 ]]; then
        local avg_per_min=$((success * 60 / duration))
        echo "  Velocidade média: ${avg_per_min} pushes/min"
    fi

    echo ""

    # Listar serviços falhados
    if [[ ${failed} -gt 0 ]]; then
        echo ""
        log_error "Serviços com falha no push:"
        for service in "${FAILED_SERVICES[@]}"; do
            echo "  - ${service}"
            echo "    Log: logs/push-${service}.log"
        done
        echo ""
    fi

    # Comandos úteis
    echo ""
    log_info "Comandos úteis:"
    echo ""
    echo "  # Verificar imagens no ECR"
    echo "  aws ecr list-images --repository-name neural-hive-${ENV}/gateway-intencoes --region ${AWS_REGION}"
    echo ""
    echo "  # Listar todos os repositórios"
    echo "  aws ecr describe-repositories --region ${AWS_REGION} | grep repositoryName"
    echo ""

    # Sair com código apropriado
    if [[ ${failed} -gt 0 ]]; then
        exit 1
    else
        exit 0
    fi
}

# ==============================================================================
# Execução
# ==============================================================================

main
