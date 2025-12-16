#!/bin/bash
# ============================================================================
# ⚠️  DEPRECATION WARNING
# ============================================================================
# Este script está deprecated e será removido em versão futura.
# Use o novo CLI unificado: ./scripts/build.sh
#
# Equivalência:
#   ./scripts/build-local-parallel.sh --version 1.0.8
#   → ./scripts/build.sh --target local --version 1.0.8
#
#   ./scripts/push-to-ecr.sh --version 1.0.8
#   → ./scripts/build.sh --target ecr --version 1.0.8
# ============================================================================

echo ""
echo "⚠️  AVISO: Este script está deprecated"
echo "   Use: ./scripts/build.sh --target <local|ecr|registry|all>"
echo "   Documentação: ./scripts/build.sh --help"
echo ""
sleep 2

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
source "${SCRIPT_DIR}/lib/docker.sh"

# Enable Docker BuildKit for improved build performance
export DOCKER_BUILDKIT=1

# Configuration
VERSION="${VERSION:-1.0.7}"
MAX_PARALLEL_JOBS="${MAX_PARALLEL_JOBS:-4}"
# Derive PROJECT_ROOT from script location (portable across environments)
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_CONTEXT="."
NO_CACHE=""
SKIP_BASE_IMAGES="false"

# Services array (9 Phase 1 services)
SERVICES=(
    "gateway-intencoes"
    "semantic-translation-engine"
    "specialist-business"
    "specialist-technical"
    "specialist-behavior"
    "specialist-evolution"
    "specialist-architecture"
    "consensus-engine"
    "memory-layer-api"
)

# Arrays for tracking
declare -a BUILD_PIDS
declare -a FAILED_SERVICES
declare -a SUCCESS_SERVICES

# Counters
total=${#SERVICES[@]}
completed=0
failed=0
success=0

# Check prerequisites
check_build_prerequisites() {
    log_info "Verificando pré-requisitos..."

    check_prerequisites

    # Check if in correct directory
    if [ ! -d "${PROJECT_ROOT}/services" ]; then
        log_error "Diretório services/ não encontrado. Execute o script da raiz do projeto."
        exit 1
    fi

    # Check disk space (at least 10GB)
    available_space=$(df -BG "${PROJECT_ROOT}" | awk 'NR==2 {print $4}' | sed 's/G//')
    if [ "${available_space}" -lt 10 ]; then
        log_warning "Espaço em disco baixo: ${available_space}GB (recomendado: 10GB+)"
    else
        log_success "Espaço em disco: ${available_space}GB"
    fi
}

# Build base images first
build_base_images_first() {
    if [ "${SKIP_BASE_IMAGES}" = "true" ]; then
        log_info "Pulando build de imagens base (--skip-base-images)"
        return 0
    fi

    log_info "Construindo imagens base primeiro..."

    if [ -f "${PROJECT_ROOT}/scripts/build-base-images.sh" ]; then
        bash "${PROJECT_ROOT}/scripts/build-base-images.sh" --version "${VERSION}" ${NO_CACHE}
        if [ $? -ne 0 ]; then
            log_error "Falha ao construir imagens base"
            exit 1
        fi
        log_success "Imagens base construídas com sucesso"
    else
        log_warning "build-base-images.sh não encontrado, pulando..."
    fi
}

# Build individual service
build_service() {
    local service_name=$1
    local dockerfile_path="services/${service_name}/Dockerfile"
    local image_name="neural-hive-mind/${service_name}"
    local log_file="logs/build-${service_name}.log"

    # Check if Dockerfile exists
    if [ ! -f "${dockerfile_path}" ]; then
        echo "ERROR: Dockerfile não encontrado: ${dockerfile_path}" >> "${log_file}"
        return 1
    fi

    # Build the image
    BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    local build_args=(
        "VERSION=${VERSION}"
        "BUILD_DATE=${BUILD_DATE}"
    )

    local cache_flag=()
    [[ -n "${NO_CACHE}" ]] && cache_flag+=(--no-cache)

    DOCKER_BUILD_SILENT=true DOCKER_BUILD_LOG_FILE="${log_file}" docker_build "${image_name}" "${VERSION}" "${dockerfile_path}" "${BUILD_CONTEXT}" "${build_args[@]}" "${cache_flag[@]}"
}

# Semaphore control for parallel jobs
acquire_slot() {
    while [ $(jobs -r | wc -l) -ge ${MAX_PARALLEL_JOBS} ]; do
        sleep 0.5
    done
}

# Show progress bar
show_progress() {
    local current=$1
    local total=$2
    local percent=$((current * 100 / total))
    local filled=$((percent / 5))
    local empty=$((20 - filled))

    printf "\r${BLUE}Progresso:${NC} ["
    printf "%${filled}s" | tr ' ' '='
    printf ">"
    printf "%${empty}s" | tr ' ' ' '
    printf "] %3d%% (%d/%d)" ${percent} ${current} ${total}
}

# Cleanup function
cleanup() {
    if [ ${#BUILD_PIDS[@]} -gt 0 ]; then
        log_warning "Interrompendo builds em andamento..."
        for pid in "${BUILD_PIDS[@]}"; do
            kill -TERM ${pid} 2>/dev/null || true
        done
    fi
    rm -rf /tmp/build-semaphore 2>/dev/null || true
}

# Print help
print_help() {
    cat << EOF
🚀 Neural Hive-Mind - Build Paralelo de Imagens Docker

Uso: $0 [opções]

Opções:
  --version <ver>       Versão das imagens (padrão: 1.0.7)
  --parallel <n>        Número de builds paralelos (padrão: 4)
  --services <list>     Buildar apenas serviços específicos (separados por vírgula)
  --no-cache            Força rebuild sem usar cache do Docker
  --skip-base-images    Pular build de imagens base (assume que já existem)
  --help                Exibe esta mensagem de ajuda

Exemplos:
  # Build padrão (4 jobs paralelos, versão 1.0.7)
  $0

  # Build com mais paralelização (8 jobs)
  $0 --parallel 8

  # Build de serviços específicos
  $0 --services "gateway-intencoes,consensus-engine"

  # Build com versão customizada
  $0 --version 1.0.8

  # Build sem cache
  $0 --no-cache

  # Build apenas serviços (imagens base já construídas)
  $0 --skip-base-images

EOF
    exit 0
}

# Parse command line arguments
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
            total=${#SERVICES[@]}
            shift 2
            ;;
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        --skip-base-images)
            SKIP_BASE_IMAGES="true"
            shift
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

# Trap signals for cleanup
trap cleanup EXIT INT TERM

# Main execution
main() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}🚀 Neural Hive-Mind - Build Paralelo de Imagens Docker${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}Versão:${NC} ${VERSION}"
    echo -e "${BLUE}Jobs paralelos:${NC} ${MAX_PARALLEL_JOBS}"
    echo -e "${BLUE}Total de serviços:${NC} ${total}"
    echo ""

    check_prerequisites

    # Build base images first
    build_base_images_first

    # Create logs directory
    mkdir -p "${PROJECT_ROOT}/logs"

    # Create semaphore directory
    mkdir -p /tmp/build-semaphore

    echo ""
    log_info "Iniciando builds paralelos..."
    echo ""

    # Record start time
    start_time=$(date +%s)

    # Start builds
    local index=1
    for service in "${SERVICES[@]}"; do
        acquire_slot

        log_info "[${index}/${total}] 🔨 ${service}"

        # Start build in background
        (
            if build_service "${service}"; then
                echo "SUCCESS:${service}" > "/tmp/build-semaphore/${service}.status"
            else
                echo "FAILED:${service}" > "/tmp/build-semaphore/${service}.status"
            fi
        ) &

        BUILD_PIDS+=($!)
        ((index++))
    done

    echo ""

    # Wait for all builds and show progress
    for pid in "${BUILD_PIDS[@]}"; do
        wait ${pid} || true
        ((completed++))
        show_progress ${completed} ${total}
    done

    echo ""
    echo ""

    # Collect results
    for service in "${SERVICES[@]}"; do
        if [ -f "/tmp/build-semaphore/${service}.status" ]; then
            status=$(cat "/tmp/build-semaphore/${service}.status")
            if [[ ${status} == SUCCESS:* ]]; then
                SUCCESS_SERVICES+=("${service}")
                ((success++))
                log_success "${service} concluído"
            else
                FAILED_SERVICES+=("${service}")
                ((failed++))
                log_error "${service} falhou (ver logs/build-${service}.log)"
            fi
        else
            FAILED_SERVICES+=("${service}")
            ((failed++))
            log_error "${service} - status desconhecido"
        fi
    done

    # Calculate duration
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    minutes=$((duration / 60))
    seconds=$((duration % 60))

    # Print summary
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}📊 RESUMO FINAL${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}✅ Builds bem-sucedidos:${NC} ${success}/${total}"
    if [ ${failed} -gt 0 ]; then
        echo -e "${RED}❌ Builds falhados:${NC} ${failed}/${total}"
    fi
    echo -e "${BLUE}⏱️  Tempo total:${NC} ${minutes}m ${seconds}s"

    if [ ${duration} -gt 0 ]; then
        builds_per_min=$(awk "BEGIN {printf \"%.1f\", ${total}/${duration}*60}")
        echo -e "${BLUE}⚡ Velocidade média:${NC} ${builds_per_min} builds/min"
    fi

    # List failed services
    if [ ${#FAILED_SERVICES[@]} -gt 0 ]; then
        echo ""
        echo -e "${RED}Serviços falhados:${NC}"
        for service in "${FAILED_SERVICES[@]}"; do
            echo -e "  ${RED}-${NC} ${service} (logs/build-${service}.log)"
        done
    fi

    echo ""
    echo -e "${BLUE}Verificar imagens:${NC}"
    echo -e "  docker images | grep neural-hive-mind"
    echo ""

    # Exit with error if any builds failed
    if [ ${failed} -gt 0 ]; then
        exit 1
    fi
}

# Change to project root
cd "${PROJECT_ROOT}"

# Run main
main
