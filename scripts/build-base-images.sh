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

# Script para build das imagens base do Neural Hive-Mind
# Constrói as imagens base em ordem de dependência: ml-base -> grpc-base -> mlops-base -> nlp-base -> specialist-base

set -euo pipefail

# Cores para output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Configurações
VERSION="${VERSION:-1.0.0}"
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NO_CACHE=""
PUSH_TO_ECR="false"

# Array de imagens base em ordem de dependência
readonly BASE_IMAGES=(
    "python-ml-base"
    "python-observability-base"
    "python-grpc-base"
    "python-mlops-base"
    "python-nlp-base"
    "python-specialist-base"
)

# Funções de logging
log_info() {
    echo -e "${BLUE}ℹ${NC} $*"
}

log_success() {
    echo -e "${GREEN}✓${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $*"
}

log_error() {
    echo -e "${RED}✗${NC} $*" >&2
}

# Função para verificar pré-requisitos
check_prerequisites() {
    log_info "Verificando pré-requisitos..."

    # Verificar se Docker está rodando
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker não está rodando ou não está acessível"
        exit 1
    fi

    # Verificar se diretório base-images existe
    if [ ! -d "${PROJECT_ROOT}/base-images" ]; then
        log_error "Diretório base-images/ não encontrado em ${PROJECT_ROOT}"
        exit 1
    fi

    # Verificar espaço em disco (mínimo 5GB)
    local available_space
    available_space=$(df "${PROJECT_ROOT}" | awk 'NR==2 {print $4}')
    local min_space=$((5 * 1024 * 1024)) # 5GB em KB

    if [ "${available_space}" -lt "${min_space}" ]; then
        log_warning "Espaço em disco pode ser insuficiente (disponível: $(($available_space / 1024 / 1024))GB)"
    fi

    log_success "Pré-requisitos verificados"
}

# Função para build de uma imagem base
build_base_image() {
    local image=$1
    local dockerfile="${PROJECT_ROOT}/base-images/${image}/Dockerfile"

    log_info "Building ${image}..."

    # Verificar se Dockerfile existe
    if [ ! -f "${dockerfile}" ]; then
        log_warning "Dockerfile não encontrado: ${dockerfile}"
        return 1
    fi

    # Build da imagem
    if docker build \
        -t "neural-hive-mind/${image}:${VERSION}" \
        -t "neural-hive-mind/${image}:latest" \
        -f "${dockerfile}" \
        --build-arg VERSION="${VERSION}" \
        --build-arg BUILD_DATE="${BUILD_DATE}" \
        ${NO_CACHE} \
        --progress=plain \
        "${PROJECT_ROOT}"; then
        log_success "${image}:${VERSION} construída com sucesso"
        return 0
    else
        log_error "Falha ao construir ${image}"
        return 1
    fi
}

# Função para push para ECR
push_to_ecr() {
    local image=$1

    if [ "${PUSH_TO_ECR}" != "true" ]; then
        return 0
    fi

    if [ -z "${ECR_REGISTRY:-}" ]; then
        log_warning "ECR_REGISTRY não definido, pulando push"
        return 0
    fi

    log_info "Pushing ${image} para ECR..."

    # Login no ECR
    if ! aws ecr get-login-password --region "${AWS_REGION:-us-east-1}" | \
        docker login --username AWS --password-stdin "${ECR_REGISTRY}" 2>/dev/null; then
        log_error "Falha no login do ECR"
        return 1
    fi

    # Tag para ECR
    local ecr_tag="${ECR_REGISTRY}/${ENV:-dev}/${image}:${VERSION}"
    docker tag "neural-hive-mind/${image}:${VERSION}" "${ecr_tag}"

    # Push
    if docker push "${ecr_tag}"; then
        log_success "${image} enviada para ECR: ${ecr_tag}"
        return 0
    else
        log_error "Falha ao enviar ${image} para ECR"
        return 1
    fi
}

# Função para exibir ajuda
print_help() {
    cat <<EOF
Uso: $0 [opções]

Script para construir imagens base do Neural Hive-Mind em ordem de dependência.

Opções:
  --version VERSION        Versão das imagens (padrão: 1.0.0)
  --no-cache               Construir sem usar cache do Docker
  --push-to-ecr            Enviar imagens para ECR após build
  --help                   Exibir esta mensagem de ajuda

Variáveis de ambiente:
  VERSION                  Versão das imagens (padrão: 1.0.0)
  ECR_REGISTRY             Registry ECR (necessário para --push-to-ecr)
  AWS_REGION               Região AWS (padrão: us-east-1)
  ENV                      Ambiente (dev/staging/prod, padrão: dev)

Exemplos:
  # Build básico com versão padrão
  $0

  # Build com versão específica
  $0 --version 1.0.1

  # Build sem cache
  $0 --no-cache

  # Build e push para ECR
  export ECR_REGISTRY=077878370245.dkr.ecr.us-east-1.amazonaws.com
  $0 --version 1.0.0 --push-to-ecr

Ordem de build:
  1. python-ml-base           (Python 3.11 + build tools)
  2. python-observability-base (ml-base + neural_hive_observability)
  3. python-grpc-base         (ml-base + gRPC/protobuf)
  4. python-mlops-base        (grpc-base + pandas/numpy/scikit-learn/mlflow)
  5. python-nlp-base          (grpc-base + spaCy + models)
  6. python-specialist-base   (nlp-base + neural_hive_specialists + common deps)

EOF
}

# Parse de argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        --push-to-ecr)
            PUSH_TO_ECR="true"
            shift
            ;;
        --help)
            print_help
            exit 0
            ;;
        *)
            log_error "Opção desconhecida: $1"
            print_help
            exit 1
            ;;
    esac
done

# Main execution
main() {
    log_info "=== Build de Imagens Base do Neural Hive-Mind ==="
    log_info "Versão: ${VERSION}"
    log_info "Data de build: ${BUILD_DATE}"
    log_info "Diretório do projeto: ${PROJECT_ROOT}"
    echo

    # Verificar pré-requisitos
    check_prerequisites
    echo

    # Contadores de sucesso/falha
    local success_count=0
    local fail_count=0

    # Build de cada imagem base em ordem
    for image in "${BASE_IMAGES[@]}"; do
        if build_base_image "${image}"; then
            ((success_count++))

            # Push para ECR se solicitado
            push_to_ecr "${image}"
        else
            ((fail_count++))
            log_error "Build falhou para ${image}, abortando..."
            exit 1
        fi
        echo
    done

    # Resumo
    echo
    log_info "=== Resumo do Build ==="
    log_success "${success_count} imagem(ns) construída(s) com sucesso"

    if [ ${fail_count} -gt 0 ]; then
        log_error "${fail_count} imagem(ns) falharam"
        exit 1
    fi

    # Listar imagens criadas
    log_info "Imagens base disponíveis:"
    docker images | grep "neural-hive-mind/python-.*-base" | head -n 10 || true

    if [ "${PUSH_TO_ECR}" = "true" ] && [ -n "${ECR_REGISTRY:-}" ]; then
        echo
        log_info "Para verificar imagens no ECR:"
        for image in "${BASE_IMAGES[@]}"; do
            echo "  aws ecr list-images --repository-name ${ENV:-dev}/${image} --region ${AWS_REGION:-us-east-1}"
        done
    fi

    echo
    log_success "Build de imagens base concluído com sucesso!"
}

# Executar main
main
